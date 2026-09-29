"""Independent assertions for accepted rich text and intrinsic SVG geometry."""
import unittest
from xml.etree import ElementTree as ET
from ansatz_slide.images import image_info, crop_attributes
from ansatz_slide.richtext import paragraphs_xml
from ansatz_slide.validation import Validator, ValidationError
from ansatz_slide.xml import NAMESPACES


def paragraphs(html, **base):
    return ET.fromstring('<root '+ ' '.join(f'xmlns:{k}="{v}"' for k,v in NAMESPACES.items())+'>'+
                         paragraphs_xml(html,base)+'</root>')


class RichTextSemanticsTests(unittest.TestCase):
    def test_breaks_preserve_run_order_instead_of_merging_text(self):
        root=paragraphs('<p>A<br/>B<br><strong>C</strong></p>')
        p=root.find('a:p',NAMESPACES)
        sequence=[(e.tag.rsplit('}',1)[-1],''.join(e.itertext())) for e in p
                  if e.tag.rsplit('}',1)[-1] in ('r','br')]
        self.assertEqual([('r','A'),('br',''),('r','B'),('br',''),('r','C')],sequence)

    def test_fixed_and_proportional_line_height_and_margins(self):
        root=paragraphs('<p style="line-height:48px; margin-left:40px; margin-right:12px">A</p>')
        prop=root.find('a:p/a:pPr',NAMESPACES)
        self.assertEqual({'marL':'508000','marR':'152400'},prop.attrib)
        self.assertEqual('4800',prop.find('a:lnSpc/a:spcPts',NAMESPACES).get('val'))
        root=paragraphs('<p style="line-height:2">A</p>',lineHeightPx=48)
        self.assertEqual('200000',root.find('.//a:spcPct',NAMESPACES).get('val'))
        self.assertIsNone(root.find('.//a:spcPts',NAMESPACES))

    def test_inline_highlight_oblique_strike_and_list_spacing(self):
        html='<ul><li style="margin-top:8px;letter-spacing:2px"><span style="background-color:#FFFF00;font-style:oblique;text-decoration:underline line-through">A</span></li></ul>'
        Validator({}).rich_text(html,'text')
        root=paragraphs(html)
        prop=root.find('.//a:rPr',NAMESPACES)
        self.assertEqual('1',prop.get('i'));self.assertEqual('sngStrike',prop.get('strike'))
        self.assertEqual('sng',prop.get('u'));self.assertEqual('200',prop.get('spc'))
        self.assertEqual('FFFF00',prop.find('a:highlight/a:srgbClr',NAMESPACES).get('val'))
        self.assertEqual('800',root.find('.//a:spcBef/a:spcPts',NAMESPACES).get('val'))

    def test_unsupported_css_is_rejected_before_export(self):
        for css in ('list-style:none','list-style-type:square','list-style-position:inside','list-style-image:url(x)'):
            with self.subTest(css=css),self.assertRaises(ValidationError):
                Validator({}).rich_text(f'<ul><li style="{css}">A</li></ul>','text')
        with self.assertRaises(ValidationError):
            Validator({}).rich_text('<span style="text-decoration:overline">A</span>','text')

    def test_latex_symbols_and_scripts_are_native_math_not_plain_unicode_runs(self):
        root=paragraphs(r'<p>Variable \(x_i\), threshold \(\alpha \geq \frac{1}{2}\).</p>')
        self.assertEqual(2,len(root.findall('.//m:oMath',NAMESPACES)))
        self.assertIsNotNone(root.find('.//m:sSub',NAMESPACES))
        self.assertIsNotNone(root.find('.//m:f',NAMESPACES))
        math=''.join(e.text or '' for e in root.findall('.//m:t',NAMESPACES))
        self.assertIn('α',math);self.assertIn('≥',math)
        plain=''.join(e.text or '' for e in root.findall('.//a:t',NAMESPACES))
        self.assertNotIn('α',plain);self.assertNotIn('≥',plain)


class SvgDimensionsTests(unittest.TestCase):
    def test_no_viewbox_uses_absolute_dimensions_and_preserves_crop_ratio(self):
        kind,w,h=image_info(b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"/>')
        self.assertEqual(('svg',200,100),(kind,w,h))
        self.assertEqual({'l':25000,'r':25000},crop_attributes({'bounds':[0,0,100,100],'fit':{'mode':'cover'}},(w,h)))
        self.assertEqual({'t':-50000,'b':-50000},crop_attributes({'bounds':[0,0,100,100],'fit':{'mode':'contain'}},(w,h)))
        self.assertEqual(('svg',192,96),image_info(b'<svg width="2in" height="72pt"/>'))
        self.assertEqual(('svg',200,100),image_info(b'<svg viewBox="0,0,200,100"/>'))

    def test_unknown_relative_or_invalid_dimensions_are_not_invented(self):
        for svg in ('<svg/>','<svg width="100%" height="50%"/>','<svg width="0" height="1"/>',
                    '<svg viewBox="0 0 nan 10"/>','<svg viewBox="0 0 0 10"/>','<svg viewBox="0 0 1"/>'):
            with self.subTest(svg=svg),self.assertRaises(ValueError):image_info(svg.encode())

    def test_actual_svg_export_honors_cover_and_contain(self):
        from ansatz_slide import export_pptx
        from zipfile import ZipFile
        from io import BytesIO
        svg=b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><rect width="200" height="100" fill="red"/></svg>'
        for mode,expected in [('cover',{'l':'25000','r':'25000'}),('contain',{'t':'-50000','b':'-50000'})]:
            page={'elements':[{'elementId':'image','elementType':'image','src':'test.svg',
                'bounds':[20,20,100,100],'fit':{'mode':mode}}]}
            data=export_pptx({'size':[960,540],'pages':[page]},{'images':{'test.svg':svg}})
            with ZipFile(BytesIO(data)) as archive:
                root=ET.fromstring(archive.read('ppt/slides/slide1.xml'))
            self.assertEqual(expected,root.find('.//a:srcRect',NAMESPACES).attrib)
