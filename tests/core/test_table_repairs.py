import unittest
import xml.etree.ElementTree as ET
from ansatz_slide.tables import table_xml


def parse(element):
    return ET.fromstring('<root xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'+table_xml(element,{})+'</root>')


class TableRepairs(unittest.TestCase):
    def table(self, rows, widths, heights, style=None):
        return dict(bounds=[0,0,400,200],rows=rows,columnWidths=widths,rowHeights=heights,style=style or {})

    def test_borders_map_clockwise_and_pair_forms(self):
        for borders, expected in [([{'width':1},None,{'width':3},None],[None,None,12700,38100]),
                                  ([{'width':2},None],[None,None,25400,25400])]:
            root=parse(self.table([[{'text':'A'}]],[1],[1],{'firstRowStyle':{'border':borders}}))
            tc=root.find('.//{*}tcPr')
            self.assertEqual([None if x.get('w') is None else int(x.get('w')) for x in list(tc)[:4]],expected)

    def test_omitted_covered_cells_keep_physical_column_and_text(self):
        root=parse(self.table([[{'text':'merged','rowSpan':2,'colSpan':2},{'text':'right'}],
                               [{'text':'below'}]],[.3,.3,.4],[.5,.5]))
        rows=root.findall('.//{*}tr')
        self.assertEqual([len(r.findall('{*}tc')) for r in rows],[3,3])
        self.assertEqual([x.text for x in root.findall('.//{*}t')],['merged','right','below'])
        cells=[r.findall('{*}tc') for r in rows]
        self.assertEqual(cells[0][0].get('gridSpan'),'2')
        self.assertEqual(cells[0][1].get('hMerge'),'1')
        self.assertEqual(cells[1][0].get('vMerge'),'1')
        self.assertEqual(cells[1][1].get('vMerge'),'1')
        self.assertEqual(cells[1][1].get('hMerge'),'1')

    def test_native_equations_are_not_certified_by_office_measurement(self):
        from ansatz_slide.typography import check_page
        from pathlib import Path
        import tempfile
        base=Path(__file__).resolve().parents[2]/'tmp/test-tmp'
        base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            elements=[{'elementId':'formula','elementType':'text','bounds':[0,0,100,40],
                       'content':{'text':r'\(x^2\)'}},
                      {'elementId':'table','elementType':'table',**self.table([[{'text':r'\(a\)'}]],[1],[1])}]
            report=check_page([960,540],{'elements':elements},{},folder)
            self.assertEqual(report['status'],'blocked')
            self.assertEqual(len(report['elements']),2)
            self.assertTrue(all(e['status']=='unverified' for e in report['elements']))

    def test_actual_pdf_table_text_loss_blocks_review(self):
        from ansatz_slide.rendering import verify_table_text
        from zipfile import ZipFile
        from pathlib import Path
        from unittest.mock import patch
        import tempfile
        base=Path(__file__).resolve().parents[2]/'tmp/test-tmp';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            folder=Path(folder);source=folder/'test.pptx'
            with ZipFile(source,'w') as z:
                z.writestr('ppt/slides/slide1.xml','<root xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:tc><a:txBody><a:p><a:r><a:t>Below</a:t></a:r></a:p></a:txBody></a:tc></root>')
            def extract(command,cwd):Path(command[-1]).write_text('Right Merged')
            with patch('ansatz_slide.rendering.shutil.which',return_value='/bin/pdftotext'),patch('ansatz_slide.rendering.run_command',side_effect=extract):
                with self.assertRaisesRegex(RuntimeError,'table text is missing'):
                    verify_table_text(source,folder/'test.pdf',folder)

    def test_failed_candidate_retains_diagnostic_and_can_be_repaired(self):
        from ansatz_slide import work_objects as work
        from pathlib import Path
        from unittest.mock import patch
        from .test_page_api import fake_render
        import tempfile
        base=Path(__file__).resolve().parents[2]/'tmp/test-tmp';base.mkdir(parents=True,exist_ok=True)
        candidate={'elements':[{'elementId':'body','elementType':'text','bounds':[10,10,100,30],'content':{'text':'Keep me'}}]}
        with tempfile.TemporaryDirectory(dir=base) as folder,patch('ansatz_slide.page_api.measure_text',return_value={'status':'passed','elements':[]}):
            with patch('ansatz_slide.page_api.render_pptx',side_effect=RuntimeError('render probe failed')):
                failed=work.create(Path(folder)/'deck',{'version':'v2','size':[960,540]},candidate)
            self.assertFalse(failed['applied'])
            diagnostic=Path(failed['issues'][-1]['diagnostic'])
            self.assertIn('render probe failed',diagnostic.read_text())
            with patch('ansatz_slide.page_api.render_pptx',side_effect=fake_render):
                repaired=work.update(failed['work'])
            self.assertTrue(repaired['applied'],repaired['issues'])
