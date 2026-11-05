"""Actual Office/font layout tests, separate from stubbed geometry/transaction tests."""
from pathlib import Path
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ansatz_slide.typography import check_page
from ansatz_slide import work_objects as work
from ansatz_slide.cli import main


@unittest.skipUnless((shutil.which('soffice') or shutil.which('libreoffice')) and shutil.which('pdftotext') and shutil.which('pdffonts'),'LibreOffice and Poppler required')
class TypographyTests(unittest.TestCase):
    def setUp(self):
        base=Path(__file__).resolve().parents[2]/'tmp/test-tmp';base.mkdir(parents=True,exist_ok=True)
        temp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(temp.cleanup);self.root=Path(temp.name)

    def element(self,ident,text,size=24,width=300,height=40,font='Arial',**content):
        return {'elementId':ident,'elementType':'text','bounds':[20,20,width,height],
                'content':{'text':text,'fontSize':size,'fontFamily':font,**content}}

    def measure(self,elements,theme=None):
        return check_page([960,540],{'elements':elements},theme or {},self.root/str(len(list(self.root.iterdir()))))

    def test_real_lists_preserve_text_and_still_measure_overflow(self):
        ul='<ul><li>First item</li><li>Second <strong>item</strong></li></ul>'
        ol='<ol><li>First item</li><li>Second item</li></ol>'
        elements=[self.element('ul',ul,height=180),self.element('ol',ol,height=180),
                  self.element('crowded',ul,height=15)]
        a,b,c=self.measure(elements)['elements']
        self.assertEqual(a['status'],'passed',a);self.assertEqual(b['status'],'passed',b)
        self.assertEqual(c['status'],'overflow',c)

    def test_same_box_different_text_and_font_size_change_actual_occupancy(self):
        short=self.element('short','Short text')
        long=self.element('long','This paragraph cannot fit inside a single small frame. '*10)
        small=self.element('small','Font metrics',size=12,height=100)
        big=self.element('big','Font metrics',size=36,height=100)
        report=self.measure([short,long,small,big]);a,b,c,d=report['elements']
        self.assertEqual('passed',a['status']);self.assertEqual('overflow',b['status'])
        self.assertGreater(b['requiredHeight'],long['bounds'][3])
        self.assertGreater(d['requiredWidth'],c['requiredWidth']*2)
        self.assertTrue(a['renderedFonts'])

    def test_width_wrap_line_spacing_and_rich_runs_are_measured(self):
        text='A sentence with several words that must wrap to new lines. '*3
        narrow=self.element('narrow',text,width=160,height=1000)
        wide=self.element('wide',text,width=600,height=1000)
        spaced=self.element('spaced',text,width=160,height=1000,lineHeightPx=60)
        rich=self.element('rich','<p>small <span style="font-size: 48pt">LARGE</span></p>',size=12,height=1000)
        a,b,c,d=self.measure([narrow,wide,spaced,rich])['elements']
        self.assertGreater(a['requiredHeight'],b['requiredHeight'])
        self.assertGreater(c['requiredHeight'],a['requiredHeight'])
        self.assertGreater(d['requiredHeight'],40)
        self.assertIn(48,[r['fontSize'] for r in d['requestedStyles']])

    def test_font_family_and_no_wrap_affect_measured_width(self):
        serif=self.element('serif','iiiiiiiiiiiiiiiiiiii',font='DejaVu Serif',height=500)
        mono=self.element('mono','iiiiiiiiiiiiiiiiiiii',font='DejaVu Sans Mono',height=500)
        nowrap=self.element('nowrap','Very long unwrapped text '*2,width=100,height=500,wrap=False)
        a,b,c=self.measure([serif,mono,nowrap])['elements']
        self.assertGreater(b['requiredWidth'],a['requiredWidth'])
        self.assertEqual('overflow',c['status']);self.assertGreater(c['requiredWidth'],100)

    def test_work_retains_overflow_and_repairs_without_deleting_text(self):
        element=self.element('body','This needs several lines in the final text frame. '*4,height=30)
        result=work.create(self.root/'deck',{'version':'v2','size':[960,540]},{'elements':[element]})
        self.assertFalse(result['applied']);self.assertEqual('blocked',result['textFit'][0]['status'])
        self.assertFalse((self.root/'deck/pptx.yaml').exists())
        repaired=work.update(result['work'],element='body',changes={'bounds':[20,20,800,350]})
        self.assertTrue(repaired['applied'],repaired['issues'])
        self.assertEqual(element['content']['text'],repaired['candidates'][0]['page']['elements'][0]['content']['text'])

    def test_deck_export_rejects_overflow_without_replacing_output(self):
        from contextlib import redirect_stdout
        from io import StringIO
        deck=self.root/'deck';deck.mkdir()
        (deck/'pptx.yaml').write_text(json.dumps({'version':'v2','size':[960,540],'pages':['one.page.yaml']}))
        (deck/'one.page.yaml').write_text(json.dumps({'elements':[self.element('body','Too much text '*80)]}))
        output=self.root/'out.pptx';output.write_bytes(b'previous artifact')
        with redirect_stdout(StringIO()) as stream:code=main(['deck','export',str(deck),'-o',str(output),'--force'])
        self.assertEqual(1,code);self.assertEqual(b'previous artifact',output.read_bytes())
        self.assertEqual('blocked',json.loads(stream.getvalue())['textFit']['status'])

    def test_rotation_measures_in_local_frame_and_vertical_is_unverified(self):
        plain=self.element('plain','Short text',height=80)
        rotated=self.element('rotated','Short text',height=80);rotated['rotation']=30
        vertical=self.element('vertical','Short text',height=80,textDirection='vertical')
        a,b,c=self.measure([plain,rotated,vertical])['elements']
        self.assertEqual(a['measuredBounds'],b['measuredBounds'])
        self.assertEqual('passed',b['status'])
        self.assertEqual('unverified',c['status'])

    def test_cjk_middle_alignment_uses_actual_frame_not_forced_top_origin(self):
        centered=self.element('center','可编辑 PPTX\n正式交付文件',size=17,width=187,height=68,
                              font='Noto Sans CJK SC',bold=True,align=['center','middle'])
        top=self.element('top','可编辑 PPTX\n正式交付文件',size=17,width=187,height=68,
                         font='Noto Sans CJK SC',bold=True,align=['center','top'])
        small=self.element('small','可编辑 PPTX\n正式交付文件',size=17,width=187,height=20,
                           font='Noto Sans CJK SC',bold=True,align=['center','middle'])
        a,b,c=self.measure([centered,top,small])['elements']
        self.assertEqual('passed',a['status'],a)
        self.assertEqual('middle',a['alignmentMeasured'])
        self.assertGreaterEqual(a['measuredBounds'][1],0)
        self.assertLess(a['unrestrictedBounds'][1],-.5)
        self.assertEqual('passed',b['status'],b)
        self.assertLess(b['measuredBounds'][1],-.5)
        self.assertGreaterEqual(b['inkBounds'][1],0)
        self.assertIn('top',b['metricOverflowEdges'])
        self.assertNotEqual('passed',c['status'])

    def test_bottom_alignment_and_wrapped_overflow_remain_checked(self):
        okay=self.element('okay','Short text',height=100,align=['left','bottom'])
        long=self.element('long','A long sentence with many wrapped words. '*20,
                          width=120,height=30,align=['left','bottom'])
        a,b=self.measure([okay,long])['elements']
        self.assertEqual('passed',a['status'],a)
        self.assertEqual('bottom',a['alignmentMeasured'])
        self.assertNotEqual('passed',b['status'])


class ListTextMatchingTests(unittest.TestCase):
    def test_only_structural_leaders_are_exempted(self):
        from ansatz_slide.richtext import RichTextParser
        from ansatz_slide.typography import matches_rendered_text
        parser=RichTextParser();parser.feed('<ul><li>Keep • literal</li><li>123. keep digits</li></ul>');parser.close()
        self.assertTrue(matches_rendered_text(parser.paragraphs,'• Keep • literal • 123. keep digits'))
        for wrong in ['• Keep literal • 123. keep digits','• Keep • literal • keep digits','• Keep • literal','Keep • literal • 123. keep digits']:
            self.assertFalse(matches_rendered_text(parser.paragraphs,wrong),wrong)
