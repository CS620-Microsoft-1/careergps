"""Reviewed compact display/measurement catalog, not résumé equivalence rules.

Each fine criterion has at most one core home per job family. Its specific tool
or facet constraints remain binding; sharing a core does not make tools equal.
"""
VERSION='careergps-compact-core-v3.0'
TARGET_COUNTS={'software_engineer':22,'data_analyst':18,'ai_engineer':23}

def item(sid,name,definition,*fine_ids):
    return {'skill_id':sid,'skill_name':name,'definition':definition,'fine_skill_ids':list(fine_ids),
        'demand_semantics':'At least one positive requirement in this core is logically necessary in the source clause.',
        'resume_evaluation':'Evaluate the original fine skill constraints. Broad core evidence never substitutes for a specifically required tool or facet.'}

def module(mid,name,*skills):return {'module_id':mid,'module_name':name,'skills':list(skills)}

CATALOG={
 'software_engineer':[
    module('programming_foundations','Programming foundations',
        item('programming','Programming & languages','Programming proficiency; specific languages remain source-bound details.',
             'programming_languages','python','java','javascript','typescript','cpp','csharp','golang','ruby','php','swift','kotlin','scala','r_programming','matlab','shell_scripting','rust','c_language','perl','julia','elixir','dart','haskell'),
        item('algorithms','Algorithms & data structures','Algorithms and/or data structures; original sub-requirements retained.','algorithms','data_structures_algorithms'),
        item('object_oriented_design','Object-oriented design','Object-oriented programming/design and explicitly requested design patterns.','object_oriented_programming','design_patterns'),
        item('ai_assisted_development','AI-assisted development','Explicit use of AI in coding or software development.','ai_assisted_development')),
    module('application_system_design','Applications & system design',
        item('system_design','System design','System/software design and architecture; do not equate distinct architectural facets.','system_design','software_architecture','software_design','software_engineering'),
        item('backend_apis','Backend & API development','Backend implementation and API work, with protocol/framework details retained.','backend_development','api_design','rest_api','graphql','api_technologies','backend_frameworks','nodejs','express','django','flask','fastapi','spring','dotnet','rails','sdk_development'),
        item('frontend','Frontend development','Web/front-end interface development, including explicitly specified frameworks.','frontend_development','frontend_frameworks','react','angular','vue','nextjs','svelte','web_technologies','html','css','ui_development'),
        item('distributed_systems','Distributed systems','Distributed systems, microservices, event-driven systems and multi-tenancy retain separate facets.','distributed_systems','microservices','event_driven_architecture','multitenancy')),
    module('databases_data','Databases & data',
        item('relational_sql','SQL & relational databases','SQL querying or relational database work; SQL proficiency and a named DB are distinct details.','sql','relational_databases','postgresql','mysql','sql_server','oracle_database','sqlite','database_systems','data_modeling'),
        item('nosql_search','NoSQL & search','Non-relational stores and search systems, evaluated against the exact requested technology.','nosql_databases','mongodb','redis','dynamodb','cassandra','elasticsearch','search_retrieval','lucene','vector_databases','hnsw','ivf_index')),
    module('engineering_quality','Engineering quality',
        item('code_quality','Code quality','Maintainable, tested and clear code; this alone does not prove testing or code-review practice.','code_quality'),
        item('testing','Software testing','Testing practice and the specific required testing tools.','software_testing','testing_tools','pytest','junit','playwright','jest','cypress'),
        item('debugging','Debugging','Debugging and troubleshooting.','debugging'),
        item('code_review','Code review','Explicit code review.','code_review'),
        item('version_control','Version control','Git or explicit version/source-control practice.','version_control','git')),
    module('delivery_infrastructure','Delivery & infrastructure',
        item('cloud','Cloud platforms','Cloud platforms and explicitly named cloud services; no provider interchangeability.','cloud_platforms','aws','azure','gcp','cloud_services','eks','sagemaker'),
        item('containers','Containers','Container technologies and orchestration, with Docker/Kubernetes constraints preserved.','container_technologies','docker','kubernetes'),
        item('delivery_automation','CI/CD & delivery automation','Build/delivery/IaC/configuration facets are grouped for display, not treated as equivalent evidence.','cicd','devops','gitops','azure_devops','infrastructure_as_code','infrastructure_as_code_tools','terraform','cloudformation','configuration_management','configuration_tools','ansible','salt','build_systems','build_tools','bazel','make','gradle','buck','pants','package_management','package_management_tools','npm','pip','air_gapped_deployment','bare_metal_provisioning')),
    module('performance_operations','Performance & operations',
        item('performance','Performance analysis','Explicit performance optimization.','performance_optimization'),
        item('observability_operations','Observability & operations','Monitoring/telemetry/operations requirements, each facet retained.','observability','observability_tools','opentelemetry','telemetry','oncall','site_reliability'),
        item('reliability','Reliability','Explicit reliability/scalability requirements.','reliability_scalability')),
    module('security','Security',
        item('security','Security','Security capabilities, with protocol and control details retained.','security','identity_protocols','hardware_security','cryptography','incident_response','code_signing','iam','bug_bounty','tls','pki','ddos_protection','scim','rbac','sso','ldap')),
 ],
 'data_analyst':[
    module('query_scripting','Queries & scripting',
        item('sql','SQL','SQL or relational-data-access requirements, preserving the exact query/database facets.','sql','relational_databases','postgresql','mysql','sql_server','oracle_database','sqlite','query_engines','trino','presto'),
        item('analytical_scripting','Analytical scripting','Analytical programming; keep the exact language, library and any-of requirements.','programming_languages','python','r_programming','sas','matlab','shell_scripting','scala','python_data_libraries','pandas','numpy'),
        item('spreadsheets','Spreadsheet analysis','Spreadsheet tool requirements.','spreadsheet_tools','excel','google_sheets')),
    module('analysis_business','Analysis & business',
        item('data_analysis','Data analysis','Explicit analysis of data.','data_analysis'),
        item('business_analytics','Business analytics','Business intelligence, product/web analytics or explicit metric definition.','business_intelligence','web_analytics','business_metrics'),
        item('requirements_analysis','Requirements analysis','Explicit analysis/translation of requirements.','requirements_analysis','problem_framing')),
    module('statistics_experiments','Statistics & experiments',
        item('statistics','Statistics','Statistical methods/knowledge; a tool or degree alone does not prove this capability.','statistics','probability'),
        item('experimentation','Experimentation','Experimentation, retaining whether design or A/B execution is requested.','experiment_design','ab_testing'),
        item('causal_inference','Causal inference','Explicit causal inference.','causal_inference')),
    module('data_preparation_modeling','Data preparation & modeling',
        item('data_pipelines','Data pipelines','Pipelines/ETL and transformation details remain separate source constraints.','data_pipelines','etl','dbt'),
        item('data_modeling','Data modeling','Data/schema modeling, not merely outputting structured JSON.','data_modeling'),
        item('data_quality','Data quality','Cleaning/quality/governance requirements retain their individual facets.','data_cleaning','data_quality','data_governance')),
    module('dashboards_visualization','Dashboards & visualization',
        item('dashboarding','Dashboard development','Building or maintaining analytical/business dashboards; not ordinary documents.','dashboarding'),
        item('data_visualization','Data visualization','Explicit data visualization; no automatic dashboard equivalence.','data_visualization'),
        item('bi_tools','Business intelligence tools','Specific BI tooling retained as mandatory, optional or example details.','bi_tools','tableau','power_bi','looker','omni','mode_analytics','hex_analytics')),
    module('platforms_automation','Platforms & automation',
        item('warehousing','Data warehousing','Data-warehouse platforms and warehousing concepts retain their facets.','data_warehousing','data_warehouses','snowflake','bigquery','redshift','teradata'),
        item('large_scale_processing','Large-scale processing','Explicit large datasets/platform processing; a tool mention is not proof of all scale skills.','large_scale_data','data_processing_frameworks','spark','pyspark','hadoop','flink','ray','hive','data_platforms','databricks'),
        item('workflow_automation','Workflow automation','Automation/orchestration requirements with exact tools retained.','automation','workflow_orchestration','airflow','flyte','dagster','prefect','workflow_engines')),
 ],
 'ai_engineer':[
    module('programming_engineering','Programming & engineering',
        item('general_programming','General programming','General programming/non-Python languages; Python demand is shown separately to avoid duplicate core scoring.','programming_languages','java','javascript','typescript','cpp','csharp','golang','ruby','php','swift','kotlin','scala','r_programming','matlab','shell_scripting','rust','c_language','perl','julia','elixir','dart','haskell'),
        item('python','Python development','Explicit Python development and Python-specific data libraries; exact facets remain.','python','python_data_libraries','pandas','numpy'),
        item('software_engineering','Software engineering','Implementation, code quality, testing, debugging and API facets retained separately in detail.','software_engineering','code_quality','software_testing','testing_tools','pytest','junit','playwright','jest','cypress','debugging','code_review','version_control','git','backend_development','api_design','api_technologies','rest_api','graphql','backend_frameworks','nodejs','express','django','flask','fastapi','spring','dotnet','rails','system_design','software_architecture','software_design','object_oriented_programming','design_patterns','data_structures_algorithms','algorithms','ai_assisted_development'),
        item('sql','SQL','Explicit SQL or relational database requirements.','sql','relational_databases','postgresql','mysql','sql_server','oracle_database','sqlite')),
    module('ml_foundations','Machine learning foundations',
        item('machine_learning','Machine learning','General ML concepts or requested ML framework constraints; facets remain distinct.','machine_learning','ml_frameworks','pytorch','tensorflow','scikit_learn','xgboost','keras','jax'),
        item('deep_learning','Deep learning','Explicit deep/neural learning.','deep_learning'),
        item('math_statistics','Mathematics & statistics','Statistics, probability and mathematical foundations, preserving individual facets.','statistics','probability','linear_algebra','numerical_analysis','optimization')),
    module('data_feature_engineering','Data & feature engineering',
        item('data_preparation','Data preparation','Cleaning, data quality and modeling requirements retain their facets.','data_cleaning','data_quality','data_governance','data_modeling'),
        item('data_pipelines','Data pipelines','Pipelines/transformation/data-processing requirements.','data_pipelines','etl','dbt','large_scale_data','data_processing_frameworks','spark','pyspark','hadoop','flink','ray','hive','data_platforms','databricks','data_warehousing','data_warehouses','snowflake','bigquery','redshift','teradata'),
        item('feature_engineering','Feature engineering','Explicit feature engineering.','feature_engineering')),
    module('training_adaptation','Training & adaptation',
        item('model_training','Model training','Explicit model training.','model_training'),
        item('fine_tuning','Fine-tuning','Explicit fine-tuning; training alone does not establish this.','model_fine_tuning')),
    module('evaluation_experiments','Evaluation & experiments',
        item('model_evaluation','Model evaluation','Explicit evaluation of model quality/performance.','model_evaluation'),
        item('experimentation','Experimentation','Experiment design/A-B/causal analysis retain their specific requirements.','experiment_design','ab_testing','causal_inference')),
    module('deployment_mlops','Deployment & MLOps',
        item('model_deployment','Model deployment & serving','Explicit deployment/serving requirements.','model_deployment'),
        item('mlops','MLOps','ML lifecycle operations and Kubeflow workflows; exact requirements retained.','mlops','kubeflow'),
        item('ai_infrastructure','AI infrastructure','Distributed/cloud/container/operational facets retain separate constraints.','distributed_systems','microservices','cloud_platforms','aws','azure','gcp','cloud_services','eks','sagemaker','container_technologies','docker','kubernetes','observability','observability_tools','opentelemetry','telemetry','gpu_computing','linux','operating_systems','windows','macos','cicd','devops','gitops','azure_devops','infrastructure_as_code','infrastructure_as_code_tools','terraform','cloudformation','reliability_scalability','performance_optimization')),
    module('generative_llm_applications','Generative AI applications',
        item('generative_ai','Generative AI','Generative AI broadly; do not equate this with a specific language-model capability.','generative_ai'),
        item('llm','Large language models','Explicit LLM knowledge/use.','llm'),
        item('rag','Retrieval-augmented generation','Explicit retrieval-augmented generation; embeddings alone do not establish RAG.','rag'),
        item('ai_agents','Agents & tool use','Agentic systems, agent frameworks and tool protocols retain their exact constraints.','ai_agents','agent_frameworks','langchain','langgraph','llamaindex','crewai','claude_agent_sdk','model_context_protocol'),
        item('prompt_engineering','Prompt engineering','Explicit prompt design/engineering.','prompt_engineering'),
        item('vector_retrieval','Vector representations & retrieval','Embeddings and vector search/storage facets remain distinct constraints.','embeddings','vector_databases','search_retrieval','lucene','hnsw','ivf_index')),
 ],
}

PROFESSIONAL=[
 item('communication','Communication','Communication/documentation facets, separately assessed from technical skills.','communication','technical_writing','customer_facing'),
 item('collaboration','Collaboration','Collaboration, stakeholder and conflict-management facets.','collaboration','stakeholder_management','conflict_management','empathy'),
 item('ownership_delivery','Ownership delivery','Ownership, prioritization, execution and delivery facets.','ownership','execution','prioritization','project_management','attention_to_detail','initiative','working_under_pressure','risk_management','agile'),
 item('problem_solving_learning','Problem solving learning','Problem solving, learning and adaptability facets retained separately.','problem_solving','learning_agility','adaptability','ambiguity_management','critical_thinking','feedback','growth_mindset'),
 item('leadership','Leadership','Leadership, mentoring, alignment and strategy facets.','leadership','mentoring','cross_functional_leadership','influence_alignment','strategic_thinking'),
]

def for_family(family):
    modules=CATALOG[family];skills=[];mapping={};module_mapping={}
    for m in modules:
        for s in m['skills']:
            record={**s,'module_id':m['module_id']};skills.append(record)
            for fine_id in s['fine_skill_ids']:
                if fine_id in mapping:raise ValueError(f'Duplicate technical mapping: {family}/{fine_id}')
                mapping[fine_id]=s['skill_id'];module_mapping[fine_id]=m['module_id']
    if len(skills)!=TARGET_COUNTS[family]:raise ValueError('Core count mismatch')
    if len({s['skill_id'] for s in skills})!=len(skills):raise ValueError('Duplicate core ID')
    professional={fine:s['skill_id'] for s in PROFESSIONAL for fine in s['fine_skill_ids']}
    if len(professional)!=sum(len(s['fine_skill_ids']) for s in PROFESSIONAL):raise ValueError('Duplicate professional mapping')
    return {'job_family':family,'modules':modules,'skills':skills,'fine_to_core':mapping,'fine_to_module':module_mapping,
        'professional_skills':PROFESSIONAL,'fine_to_professional':professional,
        'mapping_policy':'Core-affiliation incidence; source facets and tools remain individually binding. Unassigned standards become extensions, never silently deleted.'}
