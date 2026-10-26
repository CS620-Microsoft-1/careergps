"""Offline, source-preserving qualification normalization; no DB/network imports.

Ratios are posting-level incidence, not counts of words. Unresolved grammar is
retained outside all three ratio numerators rather than relabeled unspecified.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import unicodedata

VERSION='career-gps-demand-v2.0'
FAMILIES=('software_engineer','data_analyst','ai_engineer')
LEVELS={'unspecified':1,'preferred':2,'required':3}

def rx(pattern,flags=re.I):return re.compile(pattern,flags)
def norm(text):
    return unicodedata.normalize('NFKC',text.replace('™','').replace('®','')).translate(str.maketrans({'–':'-','—':'-','‑':'-','’':"'",'‘':"'",'“':'"','”':'"','\u00a0':' '}))

@dataclass(frozen=True)
class Definition:
    skill_id:str
    skill_name:str
    category:str
    group:str|None
    patterns:tuple[str,...]

# Reviewed semantic aliases, independent of any résumé or individual posting.
REPLACE={
 'python':(r'python(?:[23](?:\.\d+)?)?',),
 'cpp':(r'c\+\+(?:11|14|17|20|23)?',r'cpp'),
 'golang':(r'[Gg]olang',r'\bGo\b'),
 'r_programming':(r'r programming',r'r language',r'rstudio',r'\bR\b'),
 'javascript':(r'javascript',r'java\s*script',r'ecmascript',r'\bJS\b'),
 'ownership':(r'ownership',r'take ownership',r'work(?:ing)? independently',r'independent(?:ly)?',r'autonom(?:y|ous|ously)',r'self[- ]directed',r'own (?:problems?|outcomes?|projects?)',r'projects? from (?:beginning|start) to end'),
 'communication':(r'communication(?:s)?',r'communicat(?:e|ing) (?:with clarity|clearly|effectively|complex|technical)',r'communicat(?:e|ing).{0,35}technical (?:concepts|topics)',r'explain(?:ing)? (?:complex |technical )?(?:topics|concepts) (?:clearly|to)',r'written and (?:verbal|oral) communication'),
 'ai_assisted_development':(r'ai[- ]assisted (?:development|coding|programming)',r'ai coding assistants?',r'ai tools? to accelerate (?:development|coding)',r'using ai to accelerate development',r'using ai tools?'),
}
EXTEND={
 'code_quality':[r'well[- ]tested,?(?: and)? extensible code',r'well[- ]tested,? and extensible code',r'well[- ]structured,? maintainable',r'clean,? (?:effective|maintainable) code'],
 'feedback':[r'(?:gathering|iterating on|receiving|giving|acting on) feedback',r'give and receive feedback'],
 'learning_agility':[r'eagerness to learn',r'learn new languages?',r'continuously (?:learn|grow)',r'stay current with .{0,35}(?:technologies|developments)'],
 'collaboration':[r'collaborat(?:e|ing) (?:across|in|on)',r'work(?:ing)? (?:effectively )?(?:cross[- ]functionally|across teams|as part of a .{0,45}team)',r'work(?:ing)? with .{0,25}teams'],
 'leadership':[r'lead(?:ing)? large[- ]scale projects?',r'lead(?:ing)? (?:large[- ]scale )?engineering (?:teams|projects)'],
 'api_design':[r'(?:design(?:ing)?|building|developing) (?:clean and maintainable |thoughtful and robust |web |REST )?apis?',r'api architecture'],
 'rest_api':[r'\bREST\b'],
 'data_analysis':[r'analysing data',r'analy[sz]e .{0,20}datasets?'],
 'data_modeling':[r'(?:database|relational) schema design',r'design(?:ing)? (?:relational |database )schemas'],
 'software_testing':[r'test[- ]driven development',r'\bTDD\b',r'test coverage',r'testing software'],
 'software_architecture':[r'production architecture'],
 'debugging':[r'\bdebug\b',r'diagnos(?:e|ing) .{0,20}(?:issues|failures)'],
 'systems_programming':[r'(?:device|peripheral) drivers?',r'kernel programming'],
 'cicd':[r'\b(?:CI|CD) (?:pipelines?|workflows?|systems?)'],
 'machine_learning':[r'machine[- ]learning',r'\bML engineering\b'],
 'llm':[r'large[- ]language[- ]models?'],
 'ai_agents':[r'autonomous agents?',r'agent frameworks?',r'building agents with'],
 'model_evaluation':[r'language model evaluation',r'LLM (?:evaluation|evals?|benchmarking)',r'evaluat(?:e|ing) AI (?:systems|models)'],
 'model_deployment':[r'deploy(?:ing|ed)? (?:AI|LLM) models?',r'productionizing LLM'],
 'model_training':[r'train(?:ing)? (?:ML|AI|language|foundation) models?'],
 'technical_writing':[r'well[- ]documented code',r'creating .{0,15}documentation',r'write technical documentation'],
 'performance_optimization':[r'optimi[sz](?:e|ing) (?:system )?performance'],
 'container_technologies':[r'containeri[sz]ation',r'container image management'],
 'security':[r'secure software'],
 'customer_orientation':[r'customer[- ]focused mindset',r'customer experiences?',r"customer's problem"],
 'product_thinking':[r'product sensibility'],
 'working_under_pressure':[r'think critically under pressure'],
 'problem_solving':[r'solve .{0,20}(?:complex )?problems',r'solving complex problems'],
 'ai_assisted_development':[r'AI tools to accelerate.{0,40}(?:development|coding)',r'AI tools and systems into the engineering workflow'],
 'distributed_systems':[r'distributed[- ]systems?'],
 'object_oriented_programming':[r'object[- ]oriented languages?'],
 'version_control':[r'source[- ]control'],
 'full_stack_development':[r'full[- ]stack (?:systems?|applications?)'],
 'backend_development':[r'back[- ]end (?:systems?|applications?)'],
 'gpu_computing':[r'GPU programming',r'GPU time'],
 'model_context_protocol':[r'\bMCP\b'],
 'execution':[r'measurable business outcomes?'],
 'telemetry':[r'instrument(?:ing)? (?:new )?events?(?: or telemetry)? data',r'event instrumentation'],
}
NEW=[
 ('rust','Rust','programming_language','programming_languages',r'Rust'),
 ('c_language','C','programming_language','programming_languages',r'\bC\b'),
 ('sas','SAS','analysis_tool','statistical_tools',r'SAS'),
 ('stata','Stata','analysis_tool','statistical_tools',r'Stata'),
 ('spss','SPSS','analysis_tool','statistical_tools',r'SPSS'),
 ('perl','Perl','programming_language','programming_languages',r'Perl'),
 ('julia','Julia','programming_language','programming_languages',r'Julia'),
 ('elixir','Elixir','programming_language','programming_languages',r'Elixir'),
 ('dart','Dart','programming_language','programming_languages',r'Dart'),
 ('haskell','Haskell','programming_language','programming_languages',r'Haskell'),
 ('hugging_face','Hugging Face','ml_tool','ml_tooling',r'Hugging\s*Face'),
 ('langchain','LangChain','agent_framework','agent_frameworks',r'LangChain'),
 ('langgraph','LangGraph','agent_framework','agent_frameworks',r'LangGraph'),
 ('llamaindex','LlamaIndex','agent_framework','agent_frameworks',r'Llama\s*Index'),
 ('crewai','CrewAI','agent_framework','agent_frameworks',r'CrewAI'),
 ('claude_agent_sdk','Claude Agent SDK','agent_framework','agent_frameworks',r'Claude Agent SDK'),
 ('prompt_engineering','Prompt engineering','ai_ml',None,r'prompt engineering',r'prompt design',r'iterating on prompts'),
 ('embeddings','Embeddings','ai_ml',None,r'embeddings?'),
 ('model_fine_tuning','Model fine-tuning','ml_engineering',None,r'fine[- ]tun(?:e|ed|ing)'),
 ('model_quantization','Model quantization','ml_engineering',None,r'model quantization',r'quantization[- ]aware'),
 ('model_alignment','Model alignment','ai_ml',None,r'LLM alignment',r'model alignment',r'RLHF'),
 ('reinforcement_learning','Reinforcement learning','ai_ml',None,r'reinforcement learning'),
 ('multimodal_models','Multimodal models','ai_ml',None,r'multi[- ]?modal (?:models?|modeling|modelling|foundation models?)'),
 ('data_cleaning','Data cleaning and wrangling','data_capability',None,r'data (?:cleaning|cleansing|wrangling)'),
 ('data_quality','Data quality','data_capability',None,r'data quality'),
 ('data_governance','Data governance','data_capability',None,r'data governance'),
 ('design_patterns','Design patterns','software_engineering',None,r'design patterns?'),
 ('infrastructure_as_code','Infrastructure as code','infrastructure_as_code',None,r'infrastructure[- ]as[- ]code',r'\bIaC\b'),
 ('pytest','pytest','testing_tool','testing_tools',r'pytest'),
 ('junit','JUnit','testing_tool','testing_tools',r'JUnit'),
 ('playwright','Playwright','testing_tool','testing_tools',r'Playwright'),
 ('jest','Jest','testing_tool','testing_tools',r'Jest'),
 ('cypress','Cypress','testing_tool','testing_tools',r'Cypress'),
 ('streamlit','Streamlit','application_framework','application_frameworks',r'Streamlit'),
 ('ray','Ray','data_processing','data_processing_frameworks',r'\bRay\b'),
 ('kubeflow','Kubeflow','ml_tool','ml_tooling',r'Kubeflow'),
 ('trino','Trino','query_engine','query_engines',r'Trino'),
 ('presto','Presto','query_engine','query_engines',r'Presto'),
 ('hive','Apache Hive','data_processing','data_processing_frameworks',r'Apache Hive',r'\bHive\b'),
 ('teradata','Teradata','data_warehouse','data_warehouses',r'Teradata'),
 ('ansible','Ansible','configuration_tool','configuration_tools',r'Ansible'),
 ('salt','Salt','configuration_tool','configuration_tools',r'SaltStack',r'\bSalt\b'),
 ('windows','Windows','operating_system','operating_systems',r'Windows'),
 ('macos','macOS','operating_system','operating_systems',r'macOS',r'Mac OS'),
 ('http','HTTP','network_technology',None,r'HTTPS?'),
 ('dns','DNS','network_technology',None,r'DNS'),
 ('load_balancing','Load balancing','network_technology',None,r'load balancing'),
 ('tls','TLS/SSL','security_technology',None,r'TLS',r'SSL'),
 ('pki','Public key infrastructure','security_technology',None,r'public key infrastructure',r'\bPKI\b'),
 ('ddos_protection','DDoS protection','security_technology',None,r'DDoS protection'),
 ('signal_processing','Signal processing','systems_engineering',None,r'signal processing'),
 ('control_systems','Control systems','systems_engineering',None,r'control feedback loops?',r'control systems?'),
 ('numerical_analysis','Numerical analysis','quantitative',None,r'numerical analysis'),
 ('linear_algebra','Linear algebra','quantitative',None,r'linear algebra'),
 ('probability','Probability','quantitative',None,r'probability theory',r'probabilistic (?:models?|modeling|modelling)'),
 ('geospatial','Geospatial engineering','data_capability',None,r'geospatial engineering',r'GIS/spatial databases'),
 ('localization','Localization and mapping','systems_engineering',None,r'localization',r'HD mapping'),
 ('embedded_systems','Embedded systems','systems_engineering',None,r'embedded systems?'),
 ('robotics','Robotics','systems_engineering',None,r'robotics'),
 ('autonomous_driving','Autonomous driving','domain_knowledge',None,r'autonomous (?:driving|vehicles?)',r'self[- ]driving'),
 ('interprocess_communication','Inter-process communication','systems_engineering',None,r'inter[- ]process communication',r'\bIPC\b'),
 ('network_communication','Network communication','systems_engineering',None,r'network communication',r'inter[- ]service communication'),
 ('code_signing','Code signing','security',None,r'code[- ]signing'),
 ('bare_metal_provisioning','Bare-metal provisioning','systems_engineering',None,r'bare[- ]metal provisioning',r'PXE boot',r'cloud-init'),
 ('air_gapped_deployment','Air-gapped deployment','software_operations',None,r'air[- ]gapped',r'disconnected deployment'),
 ('rf_testing','RF testing','hardware_engineering',None,r'testing .{0,20}RF devices',r'RF testing'),
 ('environmental_testing','Environmental testing','hardware_engineering',None,r'environmental test(?:ing)? methodologies'),
 ('critical_thinking','Critical thinking','professional_skill',None,r'critical thinking',r'think critically'),
 ('empathy','Empathy','professional_skill',None,r'\bempathy\b'),
 ('initiative','Initiative','professional_skill',None,r'bias (?:to|toward|towards) action',r'proactive (?:approach|mindset)'),
 ('growth_mindset','Growth mindset','professional_skill',None,r'growth mindset'),
 ('jax','JAX','ml_framework','ml_frameworks',r'\bJAX\b'),
 ('rabbitmq','RabbitMQ','streaming_platform','streaming_platforms',r'RabbitMQ'),
 ('activemq','ActiveMQ','streaming_platform','streaming_platforms',r'ActiveMQ'),
 ('gitops','GitOps','software_delivery',None,r'GitOps'),
 ('opentelemetry','OpenTelemetry','observability_tool','observability_tools',r'OpenTelemetry'),
 ('iam','Identity and access management','security',None,r'Identity and Access Management',r'\bIAM\b'),
 ('scim','SCIM','security_technology',None,r'\bSCIM\b'),
 ('rbac','RBAC','security_technology',None,r'\bRBAC\b',r'role[- ]based access control'),
 ('sso','Single sign-on','security_technology',None,r'\bSSO\b',r'single sign[- ]on'),
 ('ldap','LDAP','security_technology',None,r'\bLDAP\b'),
 ('hnsw','HNSW','search_technology',None,r'\bHNSW\b'),
 ('ivf_index','IVF indexes','search_technology',None,r'\bIVF\b'),
 ('site_reliability','Site reliability engineering','software_operations',None,r'site reliability engineering',r'\bSRE\b'),
 ('multitenancy','Multi-tenant systems','software_engineering',None,r'multi[- ]tenant (?:systems|architectures|applications)'),
 ('eks','Amazon EKS','cloud_service','cloud_services',r'\bEKS\b'),
 ('sagemaker','SageMaker','cloud_service','cloud_services',r'SageMaker'),
 ('oncall','On-call operations','software_operations',None,r'on[- ]call'),
 ('hostap','hostAP','network_technology',None,r'hostAP'),
 ('microcontrollers','Microcontrollers','hardware_engineering',None,r'microcontrollers?'),
 ('bug_bounty','Bug bounty programs','security',None,r'bug bounty'),
 ('open_source','Open-source collaboration','software_engineering',None,r'open[- ]source projects?',r'open[- ]source contributions?'),
 ('sdk_development','SDK development','software_engineering',None,r'(?:building|developing|designing) SDKs?'),
 ('saas','SaaS systems','software_engineering',None,r'SaaS (?:systems|applications|platforms)'),
 ('ui_development','User interface development','software_engineering',None,r'(?:building|developing|implementing) (?:user interfaces|UIs?)'),
 ('azure_devops','Azure DevOps','software_delivery',None,r'Azure DevOps'),
]

GENERIC={
 'programming_languages':r'(?:programming|coding|relevant) languages?',
 'frontend_frameworks':r'front[- ]?end frameworks?',
 'backend_frameworks':r'back[- ]?end frameworks?',
 'cloud_platforms':r'cloud platforms?|public cloud|cloud providers?',
 'relational_databases':r'(?<!non-)relational databases?|RDBMS',
 'nosql_databases':r'NoSQL(?: databases?)?|non[- ]relational databases?',
 'data_warehouses':r'data warehouse platforms?',
 'data_processing_frameworks':r'distributed data processing (?:tools?|frameworks?)',
 'workflow_orchestration':r'workflow orchestration (?:tools?|platforms?)',
 'bi_tools':r'business intelligence (?:tools?|platforms?)|BI tools?',
 'spreadsheet_tools':r'spreadsheet (?:tools?|software)',
 'ml_frameworks':r'(?:machine learning|ML) (?:libraries|frameworks)',
 'build_tools':r'build (?:systems?|tools?)',
 'package_management_tools':r'package[- ]management tools?|package managers?',
 'container_technologies':r'container technologies',
 'agent_frameworks':r'agent frameworks?',
 'statistical_tools':r'statistical (?:tools|software|packages)',
 'testing_tools':r'testing tools?',
}

EXAMPLE=rx(r'\be\.g\.|\bfor example\b|\bsuch as\b|\bexamples? include\b|\b(?:technologies|languages|frameworks|tools|platforms) like\b')
INCLUSION=rx(r'\bincluding(?: but not limited to)?\b')
CHOICE=rx(r'\b(?:one or more|one|any|at least (?:one|two|three|four|five|\d+))\s+(?:of\b|[\w-]+\s+(?:language|technology|framework|tool|platform)s?\b)|\bone or more (?:areas|languages|technologies)\b|\b(?:one|two|three|four|five|\d+) or more\s+(?!years?\b|months?\b).{0,45}\b(?:of|among)\b')
REQUIRED=rx(r'(?<!not )(?<!not strictly )\b(?:required|mandatory|must have|must be|need to have)\b')
PREFERRED=rx(r'\b(?:preferred|preferably|ideally|nice[- ]to[- ]have|bonus|advantageous|a plus|strong plus|highly encouraged|strongly encouraged|even better)\b|\b(?:is|are|would be|considered)\s+(?:very |particularly )?(?:helpful|useful|beneficial)\b|\b(?:helpful|useful|beneficial)\s*(?=but\b|[,;.]|$)')
NEG=rx(r'\bno (?:prior |previous |specific )?(?:experience|knowledge|proficiency|background|expertise|need)\b|\bnot (?:strictly )?(?:required|necessary|essential|a prerequisite|expected)\b|\b(?:do|does) not (?:require|need)\b|\bwithout (?:requiring|needing)\b')
NUMBERS={'one':1,'two':2,'three':3,'four':4,'five':5}


class Engine:
    def __init__(self,base_catalog):
        items={x['skill_id']:dict(x) for x in base_catalog['skills']}
        for sid,patterns in REPLACE.items():items[sid]['patterns']=list(patterns)
        for sid,patterns in EXTEND.items():
            if sid in items:items[sid]['patterns']+=patterns
        for sid,name,category,group,*patterns in NEW:
            items[sid]={'skill_id':sid,'skill_name':name,'category':category,'group':group,'patterns':patterns}
        for sid,pattern in GENERIC.items():
            items[sid]={'skill_id':sid,'skill_name':sid.replace('_',' ').capitalize(),'category':'skill_group','group':None,'patterns':[pattern]}
        for sid,patterns in EXTEND.items():
            if sid in items and items[sid]['category']=='skill_group':items[sid]['patterns']+=patterns
        for row in list(items.values()):
            group=row.get('group')
            if group and group not in items:items[group]={'skill_id':group,'skill_name':group.replace('_',' ').capitalize(),'category':'skill_group','group':None,'patterns':[]}
        self.defs={sid:Definition(sid,row['skill_name'],row['category'],row.get('group'),tuple(row['patterns'])) for sid,row in items.items()}
        self.patterns=[(d,rx(r'(?<![A-Za-z0-9])(?:'+'|'.join(d.patterns)+r')(?![A-Za-z0-9])',0 if d.skill_id in {'golang','r_programming','c_language','rust','sas','ray','salt'} else re.I)) for d in self.defs.values() if d.patterns]
        self.parse_cached=lru_cache(maxsize=50000)(self.parse)

    def catalog(self):
        return {'analysis_version':VERSION,'skills':[{'skill_id':d.skill_id,'skill_name':d.skill_name,'category':d.category,'group':d.group,'patterns':list(d.patterns)} for d in self.defs.values()]}

    def guard(self,sid,text,start,end):
        around=text[max(0,start-50):min(len(text),end+70)];before=text[max(0,start-30):start];after=text[end:end+55]
        word=text[start:end]
        if sid=='excel' and re.match(r'\s+(?:at|in)\b',after,re.I):return 'verb_not_software'
        if sid=='react' and re.match(r'\s+(?:to|quickly|effectively|appropriately|swiftly|proactively)\b',after,re.I):return 'verb_or_source_ambiguity'
        if sid=='express' and re.match(r'\s+(?:your|their|our|ideas|thoughts|complex|technical|themselves|yourself|clearly)\b',after,re.I):return 'verb_not_framework'
        if sid=='swift' and (word=='SWIFT' or re.match(r'\s+(?:network|messaging|payments|response)\b',after,re.I)):return 'homonym_not_language'
        if sid=='javascript' and word.casefold()=='js' and start and text[start-1]=='.':return 'nested_product_suffix'
        if sid=='typescript' and word.casefold()=='ts' and (re.search(r'clearance|TS/SCI|Top Secret',text,re.I) or not re.search(r'program|cod(?:e|ing)|JavaScript|frontend|front-end|web|languages?|framework',text,re.I)):return 'typescript_abbreviation_context_unconfirmed'
        if sid=='azure' and re.match(r'\s+DevOps\b',after,re.I):return 'delivery_product_not_cloud_platform'
        if sid=='git' and word.casefold() in {'github','gitlab'} and re.match(r'\s+(?:Copilot|Duo)\b',after,re.I):return 'AI_product_not_git_proficiency'
        if sid=='golang' and word=='Go':
            if re.match(r'[- ]to[- ]market',after,re.I):return 'go_to_market_not_language'
            if not re.search(r'program|cod(?:e|ing)|languages?|Python|Java|Rust|Scala|C\+\+|backend|using|proficien|experience|expert|knowledge|development',text,re.I):return 'short_name_context_unconfirmed'
        if sid=='r_programming' and word=='R' and not re.search(r'program|languages?|Python|SQL|SAS|Scala|statistic|analysis|analytical|proficien|coding',text,re.I):return 'short_name_context_unconfirmed'
        if sid=='r_programming' and word=='R' and re.match(r'\s*&\s*D\b',after):return 'research_abbreviation_not_language'
        if sid=='c_language':
            if after.startswith(('++','#')):return 'part_of_another_language'
            if not re.search(r'program|languages?|C\+\+|C#|Python|Java|Rust|coding|embedded|software|firmware',text,re.I):return 'short_name_context_unconfirmed'
        if sid=='ownership':
            if re.match(r'\s+(?:systems?|agents?|vehicles?|driving|robots?|components?|services?|variables?|models?|samples?)\b',after,re.I):return 'system_attribute_not_personal_autonomy'
            if re.search(r'(?:independent|autonomous)$',word,re.I) and not re.search(r'skills?|ability|work|operate|deliver|lead|engineer|self|implementation',around,re.I):return 'personal_autonomy_context_unconfirmed'
        if sid=='communication' and (re.search(r'inter[- ]?(?:process|service)\s*$|network\s*$|wireless\s*$|serial\s*$',before,re.I) or re.match(r'\s+(?:protocols?|between (?:services|components|systems)|interfaces?)\b',after,re.I)):return 'technical_not_interpersonal'
        if sid=='collaboration' and re.match(r'\s+filtering\b',after,re.I):return 'algorithm_not_teamwork'
        if sid=='decision_making' and (re.match(r'\s+(?:systems?|algorithms?|agents?|models?)\b',after,re.I) or re.search(r'(?:automated|algorithmic|agent)\s*$',before,re.I)):return 'system_behavior_not_personal_judgment'
        if sid=='ambiguity_management' and re.search(r'uncertain',word,re.I) and re.search(r'quantification|calibration|probability|model',around,re.I):return 'statistical_uncertainty_not_personal_skill'
        if sid=='ai_assisted_development' and not re.search(r'cod(?:e|ing)|development|programming|engineering workflow|developer',text,re.I):return 'AI_use_not_explicit_development'
        if sid=='model_fine_tuning' and not re.search(r'model|LLM|transformer|LoRA|neural|AI|training',text,re.I):return 'fine_tuning_object_unconfirmed'
        if sid=='snowflake' and re.search(r"(?:at|join|joining|work for|working for)\s*$",before,re.I):return 'employer_name_not_platform_skill'
        if sid=='localization' and re.search(r'translat|internationali|i18n|l10n',text,re.I):return 'different_localization_sense'
        return None

    def matches(self,text):
        found=[]
        for d,pattern in self.patterns:
            for m in pattern.finditer(text):
                found.append({'skill_id':d.skill_id,'start':m.start(),'end':m.end(),'matched_text':m.group(0),'guard':self.guard(d.skill_id,text,m.start(),m.end())})
        return sorted(found,key=lambda x:(x['start'],-x['end'],x['skill_id']))

    def split_clauses(self,text):
        # Split only real top-level sentences/semicolons. e.g., Node.js, OAuth 2.0
        # and punctuation inside options remain intact.
        protected=set()
        for m in re.finditer(r'\be\.g\.|\bi\.e\.|\betc\.|\.NET\b',text,re.I):protected.update(range(m.start(),m.end()))
        spans=[];depth=0;left=0
        list_scope=bool(re.search(r'(?:one|any|two|three|\d+)\s+of (?:the following|these)|following (?:areas|technologies|skills)\s*:',text,re.I))
        for i,ch in enumerate(text):
            if ch=='(':depth+=1
            elif ch==')':depth=max(0,depth-1)
            boundary=depth==0 and (ch=='\n' or (ch==';' and not list_scope) or (ch=='.' and i not in protected and not (i and i+1<len(text) and text[i-1].isalnum() and text[i+1].isalnum())))
            if boundary:
                if text[left:i].strip():spans.append((left,i))
                left=i+1
        if text[left:].strip():spans.append((left,len(text)))
        result=[]
        for a,b in spans:
            chunk=text[a:b];parts=[];last=0;depth=0
            for m in re.finditer(r'\b(?:but|however|whereas|although)\b',chunk,re.I):
                depth=chunk[:m.start()].count('(')-chunk[:m.start()].count(')')
                suffix=chunk[m.end():]
                if depth or re.match(r'\s*not (?:limited to|only|just|required|necessary|essential|a prerequisite|strictly)',suffix,re.I):continue
                parts.append((a+last,a+m.start()));last=m.end()
            parts.append((a+last,b));result+=parts
        final=[]
        for a,b in result:
            chunk=text[a:b];last=0
            for m in re.finditer(r'\band\b',chunk,re.I):
                if chunk[:m.start()].count('(')!=chunk[:m.start()].count(')'):continue
                leftpart=chunk[last:m.start()];rightpart=chunk[m.end():]
                if ((NEG.search(leftpart) and (REQUIRED.search(rightpart) or PREFERRED.search(rightpart))) or
                    (NEG.search(rightpart) and (REQUIRED.search(leftpart) or PREFERRED.search(leftpart)))):
                    final.append((a+last,a+m.start()));last=m.end()
            final.append((a+last,b))
        return [(a,b) for a,b in final if text[a:b].strip()]

    def effective_level(self,text,inherited):
        clean=re.sub(r'\bnot (?:only|just|limited to)\b',' ',text,flags=re.I)
        required=bool(REQUIRED.search(clean));preferred=bool(PREFERRED.search(clean))
        negative=bool(NEG.search(clean))
        if preferred and negative:return 'preferred','positive_optional'
        if negative:return None,'negated'
        if required and preferred:return None,'mixed_level_needs_scope_review'
        if preferred:return 'preferred','inline_preferred'
        if required:return 'required','inline_required'
        return inherited,'source_level'

    def parse(self,value,level,categories_key):
        text=norm(value);matches=self.matches(text);review=[];expressions=[]
        category=set(categories_key)
        education_only=category=={'education'}
        accepted=[];mentions=[];duration=[]
        for m in re.finditer(r'(?:at least\s+)?(?:\d+(?:\s*[-+]\s*\d*)?|one|two|three|four|five)\s*(?:\+\s*)?years?\b',text,re.I):duration.append({'text':m.group(0),'start':m.start(),'end':m.end(),'kind':'experience_duration_not_choice'})

        def reference(m,kind,clause,lev):return {**m,'classification':kind,'level':lev,'clause':clause}
        for a,b in self.split_clauses(text):
            clause=text[a:b].strip(' ,');lev,reason=self.effective_level(clause,level)
            hits=[dict(x) for x in matches if a<=x['start']<b]
            if not hits:continue
            degree_context=('education' in category and bool(re.search(r"\b(?:degree|bachelor|master|PhD|Ph\.D|MSc|BSc|BS|MS)\b",clause,re.I))
                and not re.search(r'\b(?:experience|proficiency|expertise|skilled|knowledge|ability)\b',clause,re.I))
            if education_only or degree_context or category=={'certification'}:
                for h in hits:mentions.append(reference(h,'education_context',clause,None))
                review.append({'reason':'credential_context_not_skill_evidence','clause':clause,'skill_ids':sorted({h['skill_id'] for h in hits})});continue
            if re.search(r'\b(?:our|the) (?:current )?(?:stack|technology stack)\b|\btechnologies we use\b|\b(?:company|Discord|we) (?:mainly )?uses?\b',clause,re.I):
                for h in hits:mentions.append(reference(h,'context_only',clause,None))
                review.append({'reason':'employer_stack_not_individual_requirement','clause':clause,'skill_ids':sorted({h['skill_id'] for h in hits})});continue
            if lev is None:
                for h in hits:mentions.append(reference(h,reason,clause,None))
                if reason!='negated':review.append({'reason':reason,'clause':clause,'skill_ids':sorted({h['skill_id'] for h in hits})})
                continue
            valid=[]
            for h in hits:
                if h['guard']:
                    mentions.append(reference(h,h['guard'],clause,None))
                    if h['guard'].endswith(('unconfirmed','ambiguity')):review.append({'reason':h['guard'],'clause':clause,'skill_ids':[h['skill_id']]})
                else:valid.append(h)
            if not valid:continue
            tree=self.expression(text,a,b,valid,lev,review)
            expressions.append({'clause':clause,'level':lev,'level_basis':reason,'expression':tree})
            certain,conditional=self.project(tree)
            # All occurrences are preserved; one bad first occurrence cannot mask a later valid one.
            for h in valid:
                sid=h['skill_id'];kind='direct' if sid in certain else ('conditional_option' if sid in conditional else 'example_or_unresolved')
                item=reference(h,kind,clause,lev);mentions.append(item)
                if sid in certain:accepted.append(item)
            for sid in certain-{h['skill_id'] for h in valid}:
                accepted.append({'skill_id':sid,'start':a,'end':b,'matched_text':clause,'guard':None,'classification':'guaranteed_group_from_choice','level':lev,'clause':clause})
        if not any(x['guard'] is None for x in matches) and {'skill','competency'}&category:
            review.append({'reason':'no_catalog_match','clause':text,'skill_ids':[]})
        # Residual audit flags remain visible even when a row already matches another skill.
        mask=list(text)
        for h in matches:
            if h['guard'] is None:
                for pos in range(h['start'],h['end']):mask[pos]=' '
        residual=''.join(mask)
        unknown=sorted(set(re.findall(r'\b(?:[A-Z][a-z]+[A-Z][A-Za-z0-9]*|[A-Z]{2,}[A-Z0-9]*|[a-z][a-z0-9]*(?:[-_][a-z0-9]+)+)\b',residual)))
        stop={'AI','ML','MS','BS','PhD','STEM','IT','US','USA','UK','OR','AND','NOT','WHAT','YOU','YOUR','WHO','WITH','THE','WE','BE','TO','OF','IN','ON','AT','AS','DO','IS','CAN','SQL','ETL','LLM'}
        unknown=[x for x in unknown if x not in stop and not re.fullmatch(r'(?:hands-on|end-to-end|cross-functional|large-scale|high-quality|fast-paced|real-world|well-tested|well-defined|self-motivated|full-time)',x,re.I)]
        if unknown:review.append({'reason':'residual_terms_for_taxonomy_review','clause':text,'terms':unknown,'skill_ids':[]})
        return {'normalized_text':text,'accepted':accepted,'mentions':mentions,'expressions':expressions,'experience_durations':duration,'review_items':review}

    def expression(self,text,a,b,hits,level,review):
        """Parse bounded examples and parenthesized choices before top-level lists.

        Mixed unknown syntax is recorded as a conditional tree, not asserted as
        independent mandatory atoms. Spans refer to normalized_text explicitly.
        """
        if not hits:return {'operator':'all_of','children':[]}
        # Parentheses become single nodes in their enclosing conjunction/list.
        depth=0;left=None;spans=[]
        for pos in range(a,b):
            if text[pos]=='(':
                if depth==0:left=pos
                depth+=1
            elif text[pos]==')' and depth:
                depth-=1
                if depth==0:spans.append((left,pos+1))
        units=[];used=set()
        for pa,pb in spans:
            inner=[h for h in hits if pa<h['start']<pb]
            if inner:
                node=self.expression(text,pa+1,pb-1,inner,level,review)
                units.append({'start':pa,'end':pb,'node':node});used.update(id(h) for h in inner)
        for h in hits:
            if id(h) not in used:units.append({'start':h['start'],'end':h['end'],'node':{'operator':'criterion','skill_id':h['skill_id']}})
        units.sort(key=lambda u:(u['start'],u['end']))
        chunk=text[a:b]
        ex=EXAMPLE.search(chunk);inc=INCLUSION.search(chunk)
        marker=ex or inc
        if marker:
            cut=a+marker.start();tail=[u for u in units if u['start']>=a+marker.end()];head=[u for u in units if u['end']<=cut]
            # Nested markers are already handled in their own node.
            if tail and not any(pa<cut<pb for pa,pb in spans):
                purpose=re.search(r'\b(?:to|for)\s+(?:build(?:ing)?|develop(?:ing)?|implement(?:ing)?|design(?:ing)?|creat(?:e|ing))\b',chunk[marker.end():],re.I)
                purpose_start=a+marker.end()+purpose.start() if purpose else b
                purpose_units=[u for u in tail if u['start']>=purpose_start]
                example_units=[u for u in tail if u['start']<purpose_start]
                option_ids=self.leaves({'operator':'all_of','children':[u['node'] for u in example_units]})
                example={'operator':'examples' if ex else 'inclusion_needs_review','options':sorted(option_ids),'marker':marker.group(0),'source_span':[a+marker.start(),b]}
                group_ids={self.defs[sid].group for sid in option_ids if self.defs[sid].group}
                # No separate per-tool demand is manufactured from example mentions.
                if not head and len(group_ids)==1 and all(self.defs[sid].group in group_ids for sid in option_ids):
                    group=next(iter(group_ids));head=[{'start':a,'end':cut,'node':{'operator':'criterion','skill_id':group,'inference':'category_from_homogeneous_example_list'}}]
                if inc:review.append({'reason':'including_scope_requires_review','clause':chunk,'skill_ids':sorted(option_ids)})
                after=self.combine_units(text,purpose_start,b,purpose_units,review) if purpose_units else {'operator':'all_of','children':[]}
                return {'operator':'all_of','children':[u['node'] for u in head]+[example,after]}
        if not units:return {'operator':'all_of','children':[]}
        # Named options followed by a clear new AND requirement are separate clauses.
        # Parentheses already isolate (Python or R) and SQL without heuristics.
        cuts=[]
        for j in range(1,len(units)):
            gap=text[units[j-1]['end']:units[j]['start']]
            if re.search(r'\band\b|&',gap,re.I) and not re.search(r'\band/or\b',gap,re.I):cuts.append(j)
        top_or=[]
        for j in range(1,len(units)):
            gap=text[units[j-1]['end']:units[j]['start']]
            if re.search(r'\bor\b|/',gap,re.I):top_or.append(j)
        choice=CHOICE.search(chunk)
        # "at least 3 years" is intentionally not in CHOICE.
        if choice:
            prefix=chunk[:choice.end()]
            if not re.search(r'\b(?:of|language|framework|tool|platform|technolog|area)',prefix,re.I):choice=None
        if cuts and not choice:
            branches=[];start=0
            for j in cuts+[len(units)]:
                sub=units[start:j]
                lo=a if start==0 else units[start-1]['end']
                hi=b if j==len(units) else units[j]['start']
                branches.append(self.combine_units(text,lo,hi,sub,review))
                start=j
            return {'operator':'all_of','children':branches}
        if choice and cuts:
            # An explicit general category before (...) plus AND SQL etc.
            # A quantifier can also introduce a plain option list; unresolved
            # trailing conjunctions remain conditional instead of inflated counts.
            for j in cuts:
                previous=self.leaves(units[j-1]['node']);following=self.leaves(units[j]['node'])
                prev_groups={self.defs[sid].group for sid in previous};next_groups={self.defs[sid].group for sid in following}
                if prev_groups!=next_groups and len(following)==1 and not text[units[j-1]['end']:units[j]['start']].strip().startswith(','):
                    head=self.combine_units(text,a,units[j]['start'],units[:j],review,choice=True)
                    tail=self.combine_units(text,units[j-1]['end'],b,units[j:],review)
                    return {'operator':'all_of','children':[head,tail]}
        return self.combine_units(text,a,b,units,review,choice=bool(choice))

    def combine_units(self,text,a,b,units,review,choice=False):
        if not units:return {'operator':'all_of','children':[]}
        # A capability "using" an optional tool list remains independently
        # demanded; e.g. dashboards using Tableau or Looker.
        if not choice:
            for j in range(1,len(units)):
                gap=text[units[j-1]['end']:units[j]['start']]
                prefix=text[a:units[j-1]['end']]
                if re.search(r'\b(?:using|via|with|through)\b',gap,re.I) and not re.search(r'\bor\b|/',prefix,re.I):
                    head=self.combine_units(text,a,units[j-1]['end'],units[:j],review)
                    tail=self.combine_units(text,units[j-1]['end'],b,units[j:],review)
                    return {'operator':'all_of','children':[head,tail]}
        chunk=text[a:b];children=[u['node'] for u in units]
        connectors=[text[units[i-1]['end']:units[i]['start']] for i in range(1,len(units))]
        # A missing alias must never make the other member of an OR mandatory.
        outer_prefix=text[a:units[0]['start']];outer_suffix=text[units[-1]['end']:b]
        outside_or=bool(re.search(r'\bor\s+(?:(?:a|an|the|another)\s+)?$',outer_prefix,re.I) or re.match(r'\s*[,/]?\s*\bor\b',outer_suffix,re.I))
        alternative=choice or outside_or or any(re.search(r'\bor\b|/',gap,re.I) for gap in connectors)
        if alternative:
            # Quantifier itself/category text is not one of its own alternatives.
            scope=CHOICE.search(chunk) if choice else None
            category_nodes=[]
            for i,u in enumerate(units):
                c=u['node']
                if c.get('operator')!='criterion' or self.defs[c['skill_id']].category!='skill_group':continue
                if scope and u['end']<=a+scope.end():category_nodes.append(c)
                elif not scope and i==0 and len(units)>1 and not re.search(r'\bor\b|/',text[u['end']:units[1]['start']],re.I):category_nodes.append(c)
            options=list({json.dumps(c,sort_keys=True):c for c in children if c not in category_nodes}.values())
            number=re.search(r'\bat least\s+(one|two|three|four|five|\d+)\s+of\b',chunk,re.I)
            number=number or re.search(r'\b(one|two|three|four|five|\d+)\s+or more\b(?!\s+years?)',chunk,re.I)
            minimum=(int(number.group(1)) if number.group(1).isdigit() else NUMBERS[number.group(1).lower()]) if number else 1
            if re.search(r'\b(?:and/or)\b',chunk,re.I):minimum=1
            if not options:return {'operator':'all_of','children':category_nodes}
            # Extra unnamed alternatives or mixed prose cannot be assigned a
            # complete option cardinality from recognized tokens alone.
            gap_unknown=False
            for gap in connectors:
                cleaned=re.sub(r'\b(?:and|or|with|in|of|the|a|an|such|as|similar|equivalent|other)\b|[,/\s:&-]',' ',gap,flags=re.I)
                if cleaned.strip():gap_unknown=True
            if choice:
                # Missing names at either edge of a comma list are alternatives
                # too; recognized options cannot be assumed to be the whole set.
                leading=chunk[scope.end():max(0,units[0]['start']-a)] if scope else ''
                leading=re.sub(r'\b(?:the following|these|following|common|technologies|skills|areas)\b|[\s,:()]',' ',leading,flags=re.I)
                trailing=re.match(r'\s*,\s*(?:and\s+)?([A-Za-z][A-Za-z0-9+#_.-]*)',outer_suffix)
                if leading.strip():gap_unknown=True
                if trailing and trailing.group(1).casefold() not in {'is','are','with','for','to','in','which','where','experience','knowledge','proficiency','preferred','required'}:gap_unknown=True
            if minimum>len(options):gap_unknown=True
            if outside_or or gap_unknown or (choice and len(options)==1):
                review.append({'reason':'incomplete_or_ambiguous_option_scope','clause':chunk,'skill_ids':sorted(set().union(*(self.leaves(c) for c in options)))})
                return {'operator':'all_of','children':category_nodes+[{'operator':'unresolved_choice','minimum_matches':minimum,'children':options,'source_span':[a,b]}]}
            return {'operator':'all_of','children':category_nodes+[{'operator':'minimum_of','minimum_matches':minimum,'children':options,'source_span':[a,b]}]}
        return children[0] if len(children)==1 else {'operator':'all_of','children':children}

    def leaves(self,node):
        if node['operator']=='criterion':return {node['skill_id']}
        if node['operator'] in {'examples','inclusion_needs_review'}:return set(node['options'])
        return set().union(*(self.leaves(c) for c in node.get('children',[]))) if node.get('children') else set()

    def project(self,node):
        op=node['operator']
        if op=='criterion':return {node['skill_id']},set()
        if op in {'examples','inclusion_needs_review'}:return set(),set(node['options'])
        projections=[self.project(c) for c in node.get('children',[])]
        if op=='all_of':
            return (set().union(*(x[0] for x in projections)) if projections else set(),set().union(*(x[1] for x in projections)) if projections else set())
        if op=='unresolved_choice':return set(),self.leaves(node)
        if op=='minimum_of':
            if not projections:return set(),set()
            minimum=node['minimum_matches'];all_ids=set().union(*(self.leaves(c) for c in node['children']))
            if minimum>len(projections):return set(),all_ids
            # A skill is logically necessary iff fewer than k alternatives can
            # be met without it. Categories follow the same entailment rule.
            certain={sid for sid in all_ids if sum(sid not in part[0] for part in projections)<minimum}
            categories=set()
            for child in node['children']:
                groups={self.defs[sid].group for sid in self.leaves(child)}
                if len(groups)==1 and None not in groups:categories.add(next(iter(groups)))
            for group in categories:
                guarantees=sum(bool(self.leaves(c)) and all(self.defs[sid].group==group for sid in self.leaves(c)) for c in node['children'])
                if len(node['children'])-guarantees<minimum:certain.add(group)
            return certain,all_ids-certain
        raise ValueError(op)

    def posting(self,pid,rows):
        requirements=defaultdict(lambda:{'levels':set(),'sources':[]});mentions=defaultdict(list);reviews=[];qualifications=[]
        for index,row in sorted(rows,key=lambda pair:pair[1]['position']):
            parsed=self.parse_cached(row['value'],row['level'],tuple(sorted(row.get('categories') or [])))
            ref={'qualification_row_index':index,'position':row['position'],'qualification':row['value'],'source_level':row['level'],'evidence':row['evidence']}
            qualifications.append({**ref,'normalized_text':parsed['normalized_text'],'expressions':parsed['expressions'],'experience_durations':parsed['experience_durations']})
            for h in parsed['accepted']:
                requirements[h['skill_id']]['levels'].add(h['level']);requirements[h['skill_id']]['sources'].append({**ref,**h,'offsets_refer_to':'normalized_text'})
            for h in parsed['mentions']:mentions[h['skill_id']].append({**ref,**h,'offsets_refer_to':'normalized_text'})
            for r in parsed['review_items']:reviews.append({'job_posting_id':pid,**ref,**r})
        normalized=[]
        for sid,item in requirements.items():
            levels=sorted(item['levels'],key=lambda x:-LEVELS[x]);d=self.defs[sid]
            normalized.append({'skill_id':sid,'skill_name':d.skill_name,'category':d.category,'effective_level':levels[0],'observed_levels':levels,'sources':item['sources']})
        return {'job_posting_id':pid,'qualification_count':len(rows),'requirements':sorted(normalized,key=lambda x:x['skill_id']),
            'mentions':[{'skill_id':sid,'skill_name':self.defs[sid].skill_name,'category':self.defs[sid].category,'sources':sources} for sid,sources in sorted(mentions.items())],
            'qualification_parses':qualifications,'review_items':reviews}


def aggregate(engine,family,ids,postings):
    buckets={key:defaultdict(set) for key in ['required','preferred','unspecified','mentioned','conditional','review']}
    all_sids=set()
    for p in postings:
        pid=p['job_posting_id']
        for x in p['requirements']:buckets[x['effective_level']][x['skill_id']].add(pid);all_sids.add(x['skill_id'])
        for x in p['mentions']:
            sid=x['skill_id'];all_sids.add(sid);buckets['mentioned'][sid].add(pid)
            if any(s['classification']=='conditional_option' for s in x['sources']):buckets['conditional'][sid].add(pid)
        for r in p['review_items']:
            for sid in r.get('skill_ids',[]):buckets['review'][sid].add(pid);all_sids.add(sid)
    result=[];n=len(ids)
    for sid in sorted(all_sids):
        d=engine.defs[sid];req=buckets['required'][sid];pref=buckets['preferred'][sid]-req;unspec=buckets['unspecified'][sid]-req-pref
        row={'skill_id':sid,'skill_name':d.skill_name,'category':d.category,'denominator':n}
        for prefix,s in [('required',req),('preferred_only',pref),('unspecified',unspec)]:row[prefix+'_job_count']=len(s);row[prefix+'_ratio']=round(len(s)/n,6);row[prefix+'_job_posting_ids']=sorted(s)
        row.update(counted_job_count=len(req|pref|unspec),mentioned_job_count=len(buckets['mentioned'][sid]),
            conditional_option_job_count=len(buckets['conditional'][sid]),conditional_option_job_posting_ids=sorted(buckets['conditional'][sid]),
            review_candidate_job_count=len(buckets['review'][sid]),review_candidate_job_posting_ids=sorted(buckets['review'][sid]))
        result.append(row)
    result.sort(key=lambda x:(-x['required_ratio'],-x['preferred_only_ratio'],-x['unspecified_ratio'],x['skill_id']))
    return {'job_family':family,'total_job_count':n,'jobs_with_qualifications':sum(bool(p['qualification_count']) for p in postings),
        'jobs_without_qualifications':sum(not p['qualification_count'] for p in postings),'review_item_count':sum(len(p['review_items']) for p in postings),'skills':result}
