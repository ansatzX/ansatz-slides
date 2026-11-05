import gzip
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from ansatz_slide.occupancy import analyze, write_precheck
from ansatz_slide.page_api import check_overlap


def page(*boxes):
    return {'pageType':'content','elements':[
        {'elementId':f'e{i}','elementType':'shape','bounds':b,'shapeType':'rect'} for i,b in enumerate(boxes)]}


class OccupancyTests(unittest.TestCase):
    def test_overlap_counts_and_binary_occupancy(self):
        p=page([0,0,3,3],[2,1,3,3],[2,2,1,1])
        report,c=analyze([6,5],p)
        self.assertEqual(3,c[2*6+2]);self.assertEqual(1,c[0]);self.assertEqual(0,c[-1])
        self.assertEqual(3,report['maxOccupancy']);self.assertEqual(2,report['overlapCells'])
        self.assertEqual(3,len(report['overlaps']))
        self.assertEqual([2,1,1,2],report['overlaps'][0]['intersection'])

    def test_touching_edges_do_not_overlap(self):
        report,c=analyze([6,3],page([0,0,3,3],[3,0,3,3]))
        self.assertEqual([],report['overlaps']);self.assertEqual(0,report['overlapCells'])
        self.assertTrue(all(v==1 for v in c))

    def test_clipping_negative_bounds_rotation_and_zero_area(self):
        p=page([-2,1,3,2],[9,9,2,2],[0,0,0,2],[3,3,4,2]);p['elements'][-1]['rotation']=90
        report,c=analyze([10,10],p)
        self.assertEqual(['e0','e1'],[e['elementId'] for e in report['outOfBounds']])
        self.assertEqual(['e2'],report['degenerateBounds'])
        for a,b in zip([4,2,2,4],report['elements'][-1]['envelope']):self.assertAlmostEqual(a,b)
        self.assertEqual(1,c[1*10]);self.assertEqual(1,c[99])

    def test_fractional_raster_overlap_distinguished_from_geometry(self):
        report,c=analyze([2,1],page([0,0,.5,1],[.5,0,.5,1]))
        self.assertEqual([],report['overlaps']);self.assertEqual(1,report['overlapCells'])
        self.assertEqual([2,0],list(c))

    def test_empty_page_and_grid_size_limits(self):
        report,c=analyze([3,2],page());self.assertEqual(0,report['maxOccupancy'])
        self.assertEqual([0]*6,list(c))
        for value in [0,-1,float('nan'),float('inf')]:
            with self.assertRaises(ValueError):analyze([3,2],page(),value)
        with self.assertRaisesRegex(ValueError,'increase'):analyze([100000,100000],page())
        self.assertEqual([10,10],analyze([100,100],page(),10)[0]['matrixShape'])

    def test_exported_matrices_png_and_office_independent_command(self):
        root=Path(__file__).resolve().parents[2]/'tmp/test-tmp';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            d=Path(tmp);p=page([0,0,3,3],[2,1,3,3])
            report=write_precheck([6,5],p,d/'output')
            with gzip.open(report['files']['countMatrix'],'rt') as f:counts=[[int(v) for v in line.split()] for line in f]
            with gzip.open(report['files']['occupancyMatrix'],'rt') as f:binary=[[int(v) for v in line.split()] for line in f]
            self.assertEqual(2,counts[1][2]);self.assertEqual(1,binary[1][2]);self.assertEqual(0,binary[4][5])
            data=Path(report['files']['occupancyImage']).read_bytes()
            self.assertEqual((6,5),struct.unpack('>II',data[16:24]))
            with self.assertRaises(FileExistsError):write_precheck([6,5],p,d/'output')
            # Small valid source fixture; no Office process is allowed here.
            project=d/'project';project.mkdir()
            p['elements']=[]
            (project/'p.page.yaml').write_text(json.dumps(p))
            (project/'pptx.yaml').write_text(json.dumps({'version':'v2','size':[6,5],'pages':['p.page.yaml']}))
            before={x.name:x.read_bytes() for x in project.iterdir()}
            with patch('ansatz_slide.page_api.checks.render_pptx',side_effect=AssertionError('must not render')):
                r=check_overlap(project,1,d/'standalone')
            self.assertEqual(0,r['elementCount'])
            self.assertEqual(before,{x.name:x.read_bytes() for x in project.iterdir()})
