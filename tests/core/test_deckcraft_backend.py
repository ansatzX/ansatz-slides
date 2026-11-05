"""Optional creation backend: real editable output and fail-closed publication."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from ansatz_slide.project import export_project
from ansatz_slide.validation import ValidationError
from ansatz_slide.occupancy import png_gray


class DeckcraftBackendTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[2]/'tmp/test-tmp';root.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.manifest={'version':'v2','size':[960,540],'pages':['one.page.yaml']}
        self.page={'notes':'Speaker note 中文','elements':[
            {'elementId':'title','elementType':'text','bounds':[30,30,700,70],
             'content':{'text':'中文报告 Test','fontFamily':'Microsoft YaHei','fontSize':26,'bold':True}},
            {'elementId':'box','elementType':'shape','shapeName':'rect','bounds':[30,130,200,120],
             'fill':{'type':'solid','color':'#780373'}},
            {'elementId':'image','elementType':'image','bounds':[300,130,200,120],
             'src':'image.png','fit':{'mode':'contain'}}]}
        (self.root/'image.png').write_bytes(png_gray(20,10,bytes([128])*200))
        self.save();self.output=self.root/'report.pptx'

    def save(self):
        (self.root/'pptx.yaml').write_text(json.dumps(self.manifest))
        (self.root/'one.page.yaml').write_text(json.dumps(self.page))

    @unittest.skipUnless(shutil.which('deckcraft-cli'),'Deckcraft optional executable absent')
    def test_real_creation_preserves_editable_text_shape_image_and_notes(self):
        original={p.name:p.read_bytes() for p in self.root.iterdir()}
        result=export_project(self.root,self.output,backend='deckcraft',transition='none',allow_remote=False)
        self.assertEqual(1,result['pageCount']);self.assertEqual('deckcraft',result['backend'])
        ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
        with ZipFile(self.output) as z:
            slide=ET.fromstring(z.read('ppt/slides/slide1.xml'))
            self.assertEqual(2,len(slide.findall('.//p:sp',ns)))
            self.assertEqual(1,len(slide.findall('.//p:pic',ns)))
            self.assertIn('中文报告 Test',''.join(slide.itertext()))
            self.assertEqual({'title','box','image'},{x.get('name') for x in slide.findall('.//p:cNvPr',ns) if x.get('name') in ('title','box','image')})
            note=''.join(ET.fromstring(z.read('ppt/notesSlides/notesSlide1.xml')).itertext())
            self.assertIn('Speaker note 中文',note)
        for name,data in original.items():self.assertEqual(data,(self.root/name).read_bytes())
        self.page['elements'][0]['content']['text']='修改后的报告'
        self.save();export_project(self.root,self.output,backend='deckcraft',transition='none',force=True)
        with ZipFile(self.output) as z:self.assertIn('修改后的报告',z.read('ppt/slides/slide1.xml').decode())

    def test_unsupported_dsl_preserves_existing_delivery_without_running_backend(self):
        cases=[('richtext',lambda p:p['elements'][0]['content'].update(text='<b>rich</b>')),
               ('font mapping',lambda p:p['elements'][0]['content'].update(fontFamily={'latin':'Arial','ea':'SimHei'})),
               ('crop',lambda p:p['elements'][2].update(crop={'left':.2})),
               ('theme',lambda p:self.manifest.update(theme={'colors':{'primary':'#780373'}}))]
        for label,change in cases:
            with self.subTest(label=label):
                saved=copy.deepcopy(self.page);self.manifest.pop('theme',None)
                change(self.page);self.save();self.output.write_bytes(b'previous delivery')
                with patch('ansatz_slide.deckcraft.subprocess.run',side_effect=AssertionError('must not execute')):
                    with self.assertRaises(ValidationError):export_project(self.root,self.output,backend='deckcraft',force=True)
                self.assertEqual(b'previous delivery',self.output.read_bytes());self.page=saved

    def test_missing_tool_and_failed_process_preserve_output(self):
        self.output.write_bytes(b'previous delivery')
        with patch('ansatz_slide.deckcraft.shutil.which',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'deckcraft-cli'):export_project(self.root,self.output,backend='deckcraft',force=True)
        self.assertEqual(b'previous delivery',self.output.read_bytes())
        with patch('ansatz_slide.deckcraft.shutil.which',return_value='/fake/deckcraft-cli'),patch('ansatz_slide.deckcraft.subprocess.run',side_effect=OSError('failed')):
            with self.assertRaises(OSError):export_project(self.root,self.output,backend='deckcraft',force=True)
        self.assertEqual(b'previous delivery',self.output.read_bytes())

    def test_native_default_does_not_need_deckcraft(self):
        with patch('ansatz_slide.deckcraft.export_bytes',side_effect=AssertionError('optional backend invoked')):
            result=export_project(self.root,self.output,transition='none')
        self.assertEqual('native',result['backend'])

    def test_unsupported_sources_fail_before_office_assets_or_backend(self):
        original=copy.deepcopy(self.page)
        for label,change in [('font',lambda p:p['elements'][0]['content'].update(fontFamily={'latin':'Arial','ea':'SimHei'})),
                             ('rich text',lambda p:p['elements'][0]['content'].update(text='<strong>bold</strong>')),
                             ('theme',lambda p:self.manifest.update(theme={'colors':{'primary':'#780373'}}))]:
            with self.subTest(label=label):
                self.page=copy.deepcopy(original);self.manifest.pop('theme',None)
                change(self.page);self.save();self.output.write_bytes(b'keep delivery')
                with patch('ansatz_slide.typography.check_loaded') as measure, \
                     patch('ansatz_slide.project.resolve_images') as resolve, \
                     patch('ansatz_slide.deckcraft.export_bytes') as backend:
                    with self.assertRaisesRegex(ValidationError,'Deckcraft backend'):
                        export_project(self.root,self.output,backend='deckcraft',force=True,measure_text=True)
                measure.assert_not_called();resolve.assert_not_called();backend.assert_not_called()
                self.assertEqual(b'keep delivery',self.output.read_bytes())

    def test_unsupported_image_format_fails_before_office(self):
        (self.root/'image.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10"/>')
        self.page['elements'][2]['src']='image.svg';self.save()
        self.output.write_bytes(b'keep delivery')
        with patch('ansatz_slide.typography.check_loaded') as measure, \
             patch('ansatz_slide.deckcraft.export_bytes') as backend:
            with self.assertRaisesRegex(ValidationError,'PNG/JPEG'):
                export_project(self.root,self.output,backend='deckcraft',force=True,measure_text=True)
        measure.assert_not_called();backend.assert_not_called()
        self.assertEqual(b'keep delivery',self.output.read_bytes())
