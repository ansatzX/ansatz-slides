"""Direct geometry preserves decisions without allocating a canvas raster."""
import copy
import unittest
from unittest.mock import patch
from ansatz_slide.occupancy import check_geometry, analyze, require_pages, GeometryError
from ansatz_slide.output import compact_result


class FastGeometryTests(unittest.TestCase):
    def test_gate_without_grid_including_large_canvas(self):
        page={'elements':[{'elementId':'a','elementType':'text','bounds':[0,0,10,10]}]}
        with patch('ansatz_slide.occupancy.array',side_effect=AssertionError('raster allocation')):
            self.assertEqual('passed',require_pages([100000,100000],[page])[0]['status'])
            page['elements'].append({'elementId':'b','elementType':'text','bounds':[9,9,2,2]})
            with self.assertRaisesRegex(GeometryError,'a/b'):require_pages([100000,100000],[page])

    def test_direct_and_diagnostic_decisions_agree_for_boundaries_and_rotation(self):
        a={'elementId':'a','elementType':'text','bounds':[1,1,5,5]}
        b={'elementId':'b','elementType':'text','bounds':[6,1,5,5]}
        scenarios=[({},'passed'),({'bounds':[5.5,1,5,5]},'blocked'),
                   ({'bounds':[-1,1,5,5]},'blocked'),({'bounds':[6,1,0,5]},'blocked'),
                   ({'bounds':[6,1,0,5],'elementType':'line'},'passed'),
                   ({'rotation':45},'blocked')]
        for changes,status in scenarios:
            page={'elements':[copy.deepcopy(a),{**b,**changes}]}
            with self.subTest(changes=changes):
                direct=check_geometry([20,20],page);raster,_=analyze([20,20],page)
                self.assertEqual(status,direct['status'])
                for key,value in direct.items():self.assertEqual(value,raster[key])
        page={'elements':[a,{**b,'bounds':[2,2,5,5]}],
              'allowedOverlaps':[{'elements':['a','b'],'reason':'background label'}]}
        self.assertEqual('passed',check_geometry([20,20],page)['status'])

    def test_compact_feedback_retains_failures_and_original_evidence(self):
        full={'format':'page-work-v1','work':'/work','applied':True,
              'candidates':[{'page':{'elements':[]},'geometry':{'status':'blocked',
                  'elements':[{'elementId':'a'}],'approvedOverlaps':[], 'overlaps':[],
                  'unapprovedOverlaps':[{'elements':['a','b'],'intersection':[1,2,3,4]}]}}],
              'textFit':[{'elements':[{'elementId':'ok','status':'passed'},
                                      {'elementId':'bad','status':'blocked','requiredHeight':42}]}]}
        before=copy.deepcopy(full);short=compact_result(full)
        self.assertEqual(before,full)
        self.assertNotIn('page',short['candidates'][0])
        self.assertEqual([1,2,3,4],short['candidates'][0]['geometry']['unapprovedOverlaps'][0]['intersection'])
        self.assertEqual([{'elementId':'bad','status':'blocked','requiredHeight':42}],short['textFit'][0]['elements'])
