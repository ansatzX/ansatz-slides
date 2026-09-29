"""Opt-in stdout projection; never modifies saved evidence or acceptance gates."""
import copy
from pathlib import Path


def compact_result(result):
    result=copy.deepcopy(result)
    if result.get('format')!='page-work-v1':
        if isinstance(result.get('pages'),list):
            result['pages']=[compact_result(p) for p in result['pages']]
        return result
    result['outputMode']='compact'
    # result.json is the persisted revision evidence, not necessarily the live
    # conflict/directive response. Current status, issues and gates stay inline.
    result['revisionEvidence']=str(Path(result['work'])/'result.json') if result.get('work') else None
    for key in ('candidates','operationCandidates'):
        for item in result.get(key,[]):
            if result.get('applied'):
                item.pop('page',None)
            geometry=item.get('geometry')
            if geometry:
                geometry.pop('matrices',None)
                geometry.pop('elements',None)
    for item in result.get('blockingPages',[]):
        item.get('geometry',{}).pop('matrices',None)
        item.get('geometry',{}).pop('elements',None)
    reports=result.get('textFit',[])
    if isinstance(reports,dict):reports=[reports]
    for report in reports:
        if not isinstance(report,dict):continue
        elements=report.get('elements',[])
        report.setdefault('checkedElementCount',len(elements))
        report['elements']=[e for e in elements if e.get('status')!='passed']
    return result
