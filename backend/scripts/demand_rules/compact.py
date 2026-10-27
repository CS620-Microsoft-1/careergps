"""Source-bound compact-core incidence; never treats a category as tool equivalence."""
from collections import defaultdict
import re
from .fine import Engine as FineEngine, Definition, rx, aggregate, LEVELS, norm
from .taxonomy import for_family

EXTRA=[
    Definition('business_metrics','Business/product metrics','data_capability',None,(r'(?:business|product|core) metrics',r'metric definition',r'defin(?:e|ing) (?:business |product )?metrics',r'build(?:ing)? (?:useful )?metrics',r'\bKPIs?\b')),
    Definition('problem_framing','Problem framing','professional_skill',None,(r'problem framing',r'fram(?:e|ing) business problems',r'translat(?:e|ing) business questions')),
    Definition('omni','Omni BI','bi_tool','bi_tools',(r'\bOmni\b',)),
    Definition('mode_analytics','Mode Analytics','bi_tool','bi_tools',(r'Mode Analytics',r'\bMode\b')),
    Definition('hex_analytics','Hex Analytics','bi_tool','bi_tools',(r'\bHex\b',)),
]

class Engine(FineEngine):
    def __init__(self,base):
        super().__init__(base)
        for d in EXTRA:
            self.defs[d.skill_id]=d
            self.patterns.append((d,rx(r'(?<![A-Za-z0-9])(?:'+'|'.join(d.patterns)+r')(?![A-Za-z0-9])',0 if d.skill_id in {'omni','mode_analytics','hex_analytics'} else re.I)))

    def catalog(self):
        catalog=super().catalog()
        catalog['derived_from']=catalog['analysis_version'];catalog['analysis_version']='careergps-fine-v3.0'
        catalog['changes_from_v2']=['Bound unknown comma-list alternatives before core grouping.','Add explicitly scoped business-metric/problem-framing/BI-tool aliases.']
        return catalog

    def guard(self,sid,text,start,end):
        if sid in {'omni','mode_analytics','hex_analytics'} and not re.search(r'dashboard|analytics|business intelligence|\bBI\b|metrics|reporting|data (?:analysis|tool)',text,re.I):return 'BI_tool_context_unconfirmed'
        return super().guard(sid,text,start,end)

    def combine_units(self,text,a,b,units,review,choice=False):
        # v2 missed an unrecognized comma-list member before a trailing OR:
        # "Streamlit, Claude workflows, or web frameworks" is not Streamlit-only.
        if units:
            suffix=text[units[-1]['end']:b]
            if re.match(r'\s*,',suffix) and re.search(r'\bor\b',suffix,re.I):
                first_part=suffix[:re.search(r'\bor\b',suffix,re.I).start()]
                if not re.search(r'\b(?:which|that|where|when|because)\b',first_part,re.I):
                    list_start=0 if choice else len(units)-1
                    if not choice:
                        for j in range(len(units)-1,0,-1):
                            gap=text[units[j-1]['end']:units[j]['start']]
                            if re.search(r'\b(?:using|with|via|through|build|building|experience|ability)\b',gap,re.I):break
                            if re.search(r',|\bor\b|/',gap,re.I):list_start=j-1
                            else:break
                    target=units[list_start:]
                    leaves=set().union(*(self.leaves(u['node']) for u in target))
                    review.append({'reason':'unrecognized_comma_list_alternative','clause':text[a:b],'skill_ids':sorted(leaves)})
                    unresolved={'operator':'unresolved_choice','minimum_matches':1,'children':[u['node'] for u in target],
                        'source_span':[target[0]['start'],b],'reason':'An OR list contains unrecognized alternatives; no individual choice is asserted.'}
                    prefix=super().combine_units(text,a,units[list_start]['start'],units[:list_start],review) if list_start else {'operator':'all_of','children':[]}
                    return {'operator':'all_of','children':[prefix,unresolved]}
        return super().combine_units(text,a,b,units,review,choice)


def lift(node,mapping):
    op=node['operator']
    if op=='criterion':
        fine=node['skill_id'];target=mapping.get(fine)
        return {'operator':'criterion','skill_id':target,'fine_skill_id':fine} if target else {'operator':'outside_selected_catalog','fine_skill_id':fine}
    if op in {'examples','inclusion_needs_review'}:
        return {**node,'options':sorted({mapping[sid] for sid in node['options'] if sid in mapping}),
                'original_fine_option_ids':node['options']}
    return {**node,'children':[lift(c,mapping) for c in node.get('children',[])],
            **({'minimum_matches_applies_to':'original_fine_option_branches_not_distinct_core_ids'} if op in {'minimum_of','unresolved_choice'} else {})}

def leaves(node):
    if node['operator']=='criterion':return {node['skill_id']}
    if node['operator']=='outside_selected_catalog':return set()
    if node['operator'] in {'examples','inclusion_needs_review'}:return set(node['options'])
    return set().union(*(leaves(c) for c in node.get('children',[]))) if node.get('children') else set()

def project(node):
    op=node['operator']
    if op=='criterion':return {node['skill_id']},set()
    if op=='outside_selected_catalog':return set(),set()
    if op in {'examples','inclusion_needs_review','unresolved_choice'}:return set(),leaves(node)
    children=node.get('children',[]);parts=[project(c) for c in children]
    if op=='all_of':
        yes=set().union(*(x[0] for x in parts)) if parts else set()
        conditional=set().union(*(x[1] for x in parts)) if parts else set()
        return yes,conditional-yes
    if op=='minimum_of':
        options=set().union(*(leaves(c) for c in children)) if children else set();k=node['minimum_matches']
        if not 1<=k<=len(children):return set(),options
        # Preserve original branch count: two alternative languages mapped to
        # one programming core are not "two distinct core skills".
        yes={sid for sid in options if sum(sid not in certain for certain,_ in parts)<k}
        return yes,options-yes
    raise ValueError(f'Unknown operator {op}')


def posting(engine,family,pid,rows):
    taxonomy=for_family(family)
    maps={'core':taxonomy['fine_to_core'],'module':taxonomy['fine_to_module'],'professional':taxonomy['fine_to_professional']}
    buckets={scope:defaultdict(lambda:{'levels':set(),'sources':[]}) for scope in maps}
    conditional={scope:defaultdict(set) for scope in maps}
    details=defaultdict(lambda:{'levels':set(),'source_rows':set()})
    all_parses=[];reviews=[];seen_fine=set()
    for row_index,row in sorted(rows,key=lambda pair:pair[1]['position']):
        parsed=engine.parse_cached(row['value'],row['level'],tuple(sorted(row.get('categories') or [])))
        for m in parsed['mentions']:seen_fine.add(m['skill_id'])
        qualified={'qualification_row_index':row_index,'position':row['position'],'value':row['value'],
            'source_level':row['level'],'evidence':row['evidence'],'normalized_text':parsed['normalized_text'],
            'experience_durations':parsed['experience_durations'],'fine_mentions':parsed['mentions'],'clauses':[]}
        for m in parsed['accepted']:
            details[m['skill_id']]['levels'].add(m['level']);details[m['skill_id']]['source_rows'].add(row_index)
        for ci,clause in enumerate(parsed['expressions']):
            qclause={'clause':clause['clause'],'level':clause['level'],'level_basis':clause['level_basis'],
                'fine_expression':clause['expression'],'core_expression':lift(clause['expression'],maps['core'])}
            for scope,mapping in maps.items():
                mapped=qclause['core_expression'] if scope=='core' else lift(clause['expression'],mapping)
                certain,options=project(mapped)
                qclause[scope+'_guaranteed_ids']=sorted(certain);qclause[scope+'_conditional_ids']=sorted(options)
                for sid in certain:
                    entry=buckets[scope][sid];entry['levels'].add(clause['level'])
                    entry['sources'].append({'qualification_row_index':row_index,'position':row['position'],'clause_index':ci,
                        'level':clause['level'],'level_basis':clause['level_basis'],
                        'detail_requirement_ids':sorted(engine.leaves(clause['expression'])),
                        'evidence_location':f'qualifications[position={row["position"]}].evidence'})
                for sid in options:conditional[scope][sid].add(row_index)
            qualified['clauses'].append(qclause)
        for r in parsed['review_items']:
            reviews.append({'job_posting_id':pid,'qualification_row_index':row_index,'position':row['position'],'value':row['value'],**r})
        all_parses.append(qualified)
    core_meta={s['skill_id']:s for s in taxonomy['skills']};module_meta={m['module_id']:m for m in taxonomy['modules']};prof_meta={s['skill_id']:s for s in taxonomy['professional_skills']}
    metadata={'core':core_meta,'module':module_meta,'professional':prof_meta}
    output={'job_posting_id':pid,'job_family':family,'qualification_count':len(rows),'qualifications':all_parses,'review_items':reviews,
        'mapping_semantics':'Core/module requirement incidence, not proof that all facets are required or satisfied. Read the original fine_expression for exact tools and Boolean constraints.'}
    for scope in maps:
        records=[]
        for sid,entry in sorted(buckets[scope].items()):
            meta=metadata[scope][sid];levels=sorted(entry['levels'],key=lambda level:-LEVELS[level])
            name=meta['module_name'] if scope=='module' else meta['skill_name']
            records.append({'skill_id':sid,'skill_name':name,'effective_level':levels[0],'observed_levels':levels,'sources':entry['sources']})
        output[scope+'_requirements']=records
        output[scope+'_conditional_requirements']=[{'skill_id':sid,'qualification_row_indices':sorted(indices)} for sid,indices in sorted(conditional[scope].items())]
    output['detail_requirements']=[{'skill_id':sid,'skill_name':engine.defs[sid].skill_name,
        'effective_level':max(d['levels'],key=lambda v:LEVELS[v]),'observed_levels':sorted(d['levels'],key=lambda v:-LEVELS[v]),
        'source_row_indices':sorted(d['source_rows']),
        'core_skill_id':maps['core'].get(sid),'professional_skill_id':maps['professional'].get(sid)} for sid,d in sorted(details.items())]
    mapped=set(maps['core'])|set(maps['professional'])
    output['extension_requirement_ids']=sorted(set(details)-mapped)
    output['unassigned_mention_ids']=sorted(seen_fine-mapped)
    return output


def aggregate_compact(family,postings):
    taxonomy=for_family(family);n=len(postings);result={}
    for scope,entries in [('core',taxonomy['skills']),('module',taxonomy['modules']),('professional',taxonomy['professional_skills'])]:
        buckets={level:defaultdict(set) for level in LEVELS};condition=defaultdict(set);source_ref=defaultdict(list)
        for p in postings:
            pid=p['job_posting_id']
            for row in p[scope+'_requirements']:
                sid=row['skill_id'];buckets[row['effective_level']][sid].add(pid)
                source_ref[sid].append({'job_posting_id':pid,'effective_level':row['effective_level']})
            for row in p[scope+'_conditional_requirements']:condition[row['skill_id']].add(pid)
        output=[]
        for meta in entries:
            sid=meta['module_id'] if scope=='module' else meta['skill_id'];name=meta['module_name'] if scope=='module' else meta['skill_name']
            record={'skill_id':sid,'skill_name':name,'denominator':n,'required_job_count':0,'required_ratio':0.0,'preferred_only_job_count':0,'preferred_only_ratio':0.0,'unspecified_job_count':0,'unspecified_ratio':0.0}
            for level,prefix in [('required','required'),('preferred','preferred_only'),('unspecified','unspecified')]:
                ids=buckets[level][sid]
                record[prefix+'_job_count']=len(ids);record[prefix+'_ratio']=round(len(ids)/n,6) if n else None;record[prefix+'_job_posting_ids']=sorted(ids)
            record['counted_job_count']=sum(record[k+'_job_count'] for k in ['required','preferred_only','unspecified'])
            record['conditional_option_job_count']=len(condition[sid]);record['conditional_option_job_posting_ids']=sorted(condition[sid])
            if scope=='core':record.update(module_id=meta['module_id'],definition=meta['definition'],detail_skill_ids=meta['fine_skill_ids'],resume_evaluation=meta['resume_evaluation'])
            if scope=='module':record.update(core_skill_ids=[s['skill_id'] for s in meta['skills']],interpretation='At least one mapped requirement in this module is necessary under the source logic; not all child skills are mandatory.')
            output.append(record)
        result[scope]=output
    return {'job_family':family,'total_job_count':n,'core_skill_count':len(result['core']),'module_count':len(result['module']),
        'professional_skill_count':len(result['professional']),'jobs_with_qualifications':sum(bool(p['qualification_count']) for p in postings),
        'jobs_without_qualifications':sum(not p['qualification_count'] for p in postings),
        'skills':result['core'],'modules':result['module'],'professional_skills':result['professional']}
