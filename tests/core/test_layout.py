"""Local layout preserves content and groups, refusing impossible placement."""
import copy
import unittest
from ansatz_slide.layout import apply_layout


def element(ident, bounds, kind='shape'):
    return {'elementId':ident,'elementType':kind,'bounds':bounds,
            'content':{'text':'Keep this','fill':'#123456'},'custom':{'preserve':True}}


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.page={'notes':'Keep notes','elements':[
            element('box',[10,20,100,50]),element('text',[20,30,80,30],'text'),
            element('b',[200,20,80,40]),element('untouched',[800,400,50,50])]}

    def test_row_translates_group_and_distributes_remaining_space(self):
        before=copy.deepcopy(self.page)
        out=apply_layout(self.page,[{'kind':'row','items':[['box','text'],'b'],'bounds':[50,100,300,70]}])
        a,t,b,u=out['elements']
        self.assertEqual([50,110,100,50],a['bounds'])
        self.assertEqual([60,120,80,30],t['bounds'])
        self.assertEqual([270,115,80,40],b['bounds'])
        self.assertEqual(before,self.page)
        for old,new in zip(before['elements'],out['elements']):
            self.assertEqual({k:v for k,v in old.items() if k!='bounds'}, {k:v for k,v in new.items() if k!='bounds'})
        self.assertEqual(before['elements'][-1],u)

    def test_column_fixed_gap_end_alignment(self):
        out=apply_layout(self.page,[{'kind':'column','items':['box','b'],'bounds':[30,100,160,150],'gap':15,'align':'end'}])
        self.assertEqual([90,100,100,50],out['elements'][0]['bounds'])
        self.assertEqual([110,165,80,40],out['elements'][2]['bounds'])

    def test_weighted_segments_preserve_styles_and_exact_total(self):
        out=apply_layout(self.page,[{'kind':'segments','items':['box','b'],'bounds':[50,50,300,30],'weights':[2,1]}])
        self.assertEqual([50,50,200,30],out['elements'][0]['bounds'])
        self.assertEqual([250,50,100,30],out['elements'][2]['bounds'])
        vertical=apply_layout(self.page,[{'kind':'segments','axis':'y','items':['box','b'],'bounds':[50,50,30,302],'gap':2,'weights':[2,1]}])
        self.assertEqual([50,252,30,100],vertical['elements'][2]['bounds'])

    def test_bad_inputs_cannot_partially_mutate_source(self):
        original=copy.deepcopy(self.page)
        valid={'kind':'row','items':['box','b'],'bounds':[0,0,300,100]}
        bad=[dict(valid,items=['box','missing']),dict(valid,items=['box','box']),
             dict(valid,bounds=[0,0,120,100]),dict(valid,gap=300),
             dict(valid,bounds=[0,0,float('nan'),100]),dict(valid,extra=1),
             {'kind':'segments','items':['box','b'],'bounds':[0,0,300,100],'weights':[1,0]},
             {'kind':'segments','items':['text'],'bounds':[0,0,300,100],'weights':[1]}]
        for operation in bad:
            with self.subTest(operation=operation),self.assertRaises(ValueError):apply_layout(self.page,[valid,operation])
            self.assertEqual(original,self.page)

    def test_rotations_require_explicit_handling(self):
        self.page['elements'][0]['rotation']=45
        with self.assertRaisesRegex(ValueError,'rotated'):
            apply_layout(self.page,[{'kind':'row','items':['box'],'bounds':[0,0,300,100]}])

    def test_seventeen_segments_have_shared_boundaries_and_pass_geometry(self):
        from ansatz_slide.occupancy import analyze
        page={'elements':[element(str(n),[0,0,1,1]) for n in range(17)]}
        for axis,bounds,gap in [('x',[0,0,960,100],0),('x',[10,20,950,100],1.25),
                                ('y',[20,10,100,530],0.75)]:
            with self.subTest(axis=axis,bounds=bounds,gap=gap):
                result=apply_layout(page,[{'kind':'segments','items':[str(n) for n in range(17)],
                    'weights':[1]*17,'bounds':bounds,'axis':axis,'gap':gap}])
                index=0 if axis=='x' else 1
                boxes=[e['bounds'] for e in result['elements']]
                self.assertEqual(bounds[index]+bounds[index+2],boxes[-1][index]+boxes[-1][index+2])
                for a,b in zip(boxes,boxes[1:]):
                    self.assertEqual(a[index]+a[index+2]+gap,b[index])
                report,_=analyze([960,540],result)
                self.assertEqual('passed',report['status'],report)
