"""Build criterion permissions from confirmed resume text before inference."""

from collections import Counter
from math import log
import re

from app.services.skill_gaps.skill_groups import GROUPS, GROUP_SKILLS
from app.services.skill_gaps.sources import build_index

from . import _rubric as rubric


# Generic rubric prose and resume verbs provide little skill discrimination.
STOP_WORDS = set("""
a about across actually all also an and another any applicable applicant apply
basic be behavior belongs build case check claims clearly concept condition
concrete context could data described design detail details do during eligible
else end establish evidence example explicit explicitly follow for from had has
have how i identification identify identified implementation implemented in
include including input into is it its just knowledge level local may mean
membership method model my named native new no not of on one only or original
other our own particular performed personal personally possible practice process
project qualifying relevant require required result same select selected
similar some specific stated step support task team text than that the their
them this through to tool under unknown unspecified up use used using validate
via was were what when where which while who why with without work workload
""".split())

# General vocabulary expansions, applied only to skills whose own rule mentions
# the corresponding term. Whole words avoid substring hits such as R in API.
CONCEPTS = (
    "python pandas numpy scipy matplotlib pytorch opencv",
    "sql relational postgresql postgres mysql sqlite joins",
    "programming javascript typescript java kotlin python ruby rust swift cpp csharp",
    "statistical statistics hypothesis pvalue regression probability inference",
    "neural deep cnn transformer yolo resnet lstm",
    "fine tuning lora qlora adapters pretrained finetuning",
    "generative generation diffusion gpt llama language model ollama",
    "vision language multimodal florence transformers",
    "retrieval search retriever bm25 similarity ranking",
    "vector embedding cosine faiss pinecone chroma similarity",
    "data cleaning normalization deduplication imputation labeling preprocessing",
    "container docker kubernetes k8s pod image",
    "cloud aws azure gcp ec2 lambda s3",
    "compute resource infrastructure gpu cpu memory workers distributed hardware",
    "pipeline ingestion etl airflow dagster batch dbt",
    "source version git github gitlab merge rebase commits",
    "api endpoint route rest fastapi flask http express",
    "frontend client browser react vue angular css html",
    "oriented class interface encapsulation polymorphism composition",
    "algorithm complexity trees hash sorting graph heap stack",
    "test testing assertion assertions verified confirmed pytest junit",
    "monitoring observability telemetry logs traces metrics alerts",
    "security authentication authorization access oauth vulnerabilities",
    "spreadsheet excel sheets xlsx pivot vlookup",
    "bi tableau powerbi dashboard looker",
    "warehouse snowflake bigquery redshift warehousing",
    "distributed spark pyspark hadoop partition workers parallel",
    "automation automated scheduler scheduled workflow recurring",
)

_RANKING_VERSION = "entry-level-activity-action-aware.v2"

# This vocabulary covers ordinary resume verbs. Matching an action contributes
# to ranking; it does not decide eligibility, execution, or personal ownership.
_ACTION_FAMILIES = (
    "adapt adapts adapted adapting adaptation",
    "analyze analyzes analyzed analyzing analyse analyses analysed analysing analysis",
    "automate automates automated automating automation",
    "build builds built building",
    "check checks checked checking verify verifies verified verifying verification",
    "clean cleans cleaned cleaning",
    "compare compares compared comparing comparison comparisons",
    "configure configures configured configuring configuration",
    "deploy deploys deployed deploying deployment",
    "design designs designed designing",
    "diagnose diagnoses diagnosed diagnosing diagnosis",
    "evaluate evaluates evaluated evaluating evaluation",
    "experiment experiments experimented experimenting experimentation",
    "extract extracts extracted extracting extraction",
    "fit fits fitted fitting",
    "generate generates generated generating generation generative",
    "implement implements implemented implementing implementation",
    "integrate integrates integrated integrating integration",
    "label labels labeled labelled labeling labelling",
    "launch launches launched launching",
    "maintain maintains maintained maintaining maintenance",
    "measure measures measured measuring measurement",
    "monitor monitors monitored monitoring",
    "operate operates operated operating operation",
    "optimize optimizes optimized optimizing optimise optimises optimised optimising optimization optimisation",
    "process processes processed processing",
    "query queries queried querying",
    "reconcile reconciles reconciled reconciling reconciliation",
    "retrieve retrieves retrieved retrieving retrieval",
    "review reviews reviewed reviewing",
    "run runs ran running execute executes executed executing execution",
    "schedule schedules scheduled scheduling",
    "serve serves served serving",
    "test tests tested testing exercised exercising validator validate validates validated validating validation",
    "train trains trained training",
    "transform transforms transformed transforming transformation",
    "tune tunes tuned tuning finetune finetuned finetuning",
    "update updates updated updating",
    "visualize visualizes visualized visualizing visualise visualises visualised visualising visualization visualisation",
    "write writes wrote written writing",
)
_ACTION_FORMS = {
    form: row.split()[0] for row in _ACTION_FAMILIES for form in row.split()
}
_GENERIC_ACTIONS = {"build", "check", "design", "implement", "operate", "process", "run", "update", "write"}
_DOMAIN_CONCEPTS = tuple(CONCEPTS) + (
    "lifecycle mlops train version reproducible experiment tracking orchestration monitor delivery",
    "generative diffusion autoregressive instruction llm gpt llama lora prompt response answer token multiturn",
    "experiment ablation baseline treatment control compare trial hypothesis metric benchmark",
    "serving endpoint deploy inference runtime container fastapi flask onnx tensorflow torchserve",
    "neural transformer fine-tuning adapters attention quantization yolov8 convolutional",
    "testing test fixture assertion mock unit integration regression coverage",
    "generative generation transcribe caption synthesize synthesis image transcription handwriting vlm",
    "mlops lifecycle repeatable reproducible workflow versioning monitoring registry artifact",
    "experimentation comparative compare evaluate ablation experiment baseline benchmark hypothesis",
)
# Remove ubiquitous nouns from the ranking query while retaining skill names.
_GENERIC_TERMS = {
    "application", "at", "before", "c1", "component", "configure", "describe",
    "development", "experience", "framework", "identified", "least", "linked", "logic",
    "mechanism", "model", "operate", "qualify", "software", "such", "supported",
    "system", "technical", "use", "work", "working", "workflow",
}
_THIRD_PARTY_SUBJECT = re.compile(
    r"^\s*(?:an? |the |my |our |another )?(?:team\s*mates?|colleagues?|coworkers?|co-workers?|"
    r"other (?:engineers?|developers?|analysts?|people))\b",
    re.IGNORECASE,
)


def _terms(value):
    words, actions = set(), set()
    # Normalize common capitalized/digit technology suffixes such as YOLOv8,
    # while retaining the exact token and never touching the source text.
    raw = re.findall(r"[a-z][a-z0-9]*", value.lower())
    for word in raw:
        if word in _ACTION_FORMS:
            actions.add(_ACTION_FORMS[word])
            words.add(_ACTION_FORMS[word])
            continue
        if word in STOP_WORDS or (len(word) < 2 and word != "r"):
            continue
        if len(word) > 4 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
            word = word[:-1]
        words.add(word)
        version_root = re.fullmatch(r"([a-z]{3,}?)(?:v\d+|\d+)", word)
        if version_root:
            words.add(version_root.group(1))
    return words, actions


def _source_title(source):
    return _terms(" ".join(
        value for key, value in source["context"].items()
        if key in {"name", "title", "role", "degree", "major"} and isinstance(value, str)
    ))[0]


def _claim_parts(text):
    parts = re.split(r"[.!?;](?:\s+|$)|,\s*(?:but\s+|while\s+)?(?=I\b)", text)
    return [(*_terms(part), bool(_THIRD_PARTY_SUBJECT.match(part))) for part in parts if part.strip()]


def _profile(card, rule, concepts):
    name, _ = _terms(card["skill_id"] + " " + card["skill_name"])
    core, actions = _terms(rule["core_boundary"])
    direct, _ = _terms(card["direct_evidence"])
    method, _ = _terms(" ".join(rule["criteria"][1]["supported_when"]))
    specific_actions = actions - _GENERIC_ACTIONS
    weights = {term: 0.8 for term in method - _GENERIC_TERMS - actions}
    weights.update(dict.fromkeys(direct - _GENERIC_TERMS - actions, 1.2))
    weights.update(dict.fromkeys(core - _GENERIC_TERMS - actions, 1.8))
    weights.update(dict.fromkeys(name - _GENERIC_TERMS, 2.8))
    for concept in concepts:
        if concept & (name - _GENERIC_TERMS - _GENERIC_ACTIONS) or len(concept & (core - _GENERIC_TERMS - actions)) >= 2:
            for term in concept - _GENERIC_TERMS - _GENERIC_ACTIONS:
                weights.setdefault(term, 0.85)
    specific_terms = set(weights) - set(_ACTION_FORMS.values())
    return weights, name, specific_terms, specific_actions


def _rank_activity(profile, source, allowed, parts, titles, idf):
    weights, name, specific_terms, specific_actions = profile
    title = titles[source["id"]]
    title_score = 0.15 * sum(weights[token] * idf[token] for token in sorted(title & weights.keys()))
    scores, direct_action = [], False
    for unit in source["units"]:
        if unit["kind"] not in allowed:
            continue
        clause_scores = []
        for words, actions, third_party in parts[unit["id"]]:
            hits = words & weights.keys()
            action_hits = actions & specific_actions
            lexical_score = sum(weights[token] * idf[token] for token in sorted(hits))
            has_mechanism = bool(words & specific_terms)
            if unit["kind"] == "claim" and not third_party:
                if has_mechanism and actions:
                    lexical_score += 1.25
                if action_hits:
                    lexical_score += min(2, len(action_hits)) * 3.0
                    direct_action = True
            clause_scores.append(lexical_score * (0.20 if third_party else 1.0))
        lexical_score = max(clause_scores, default=0.0)
        # A title only contributes when a source line has its own match.
        if lexical_score > 0:
            scores.append(lexical_score)
    if not scores:
        return 0.0, False
    scores.sort(reverse=True)
    return scores[0] + 0.33 * sum(scores[1:3]) + title_score + 0.1 * len(title & name), direct_action


def _shortlist(ranked, knowledge):
    if not ranked:
        return []
    if knowledge:
        return ranked[:2]

    score, direct, _ = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
    # A clear core-action match with a substantial margin needs one activity.
    # Otherwise keep up to three plausible activities so the same Agent can
    # adjudicate alternatives. An unrelated title alone is never shortlisted.
    if direct and score >= 8.0 and runner_up < score * 0.45:
        return ranked[:1]
    return [entry for entry in ranked if entry[0] >= score * 0.25 or entry[1]][:3]


def _select_activity_candidates(base_input):
    """Build ordered validator-compatible candidates and auditable coverage flags."""
    family = base_input["job_family"]
    sources = base_input["resume_sources"]
    index = build_index(sources)
    catalog = rubric._catalog(family)
    cards = base_input["core_skills"]
    if len(cards) != len(catalog) or {card["skill_id"] for card in cards} != set(catalog):
        raise ValueError("Selector input must cover exactly the confirmed family skill catalog")

    terms = {uid: _terms(unit["text"]) for uid, unit in index.items()}
    parts = {uid: _claim_parts(unit["text"]) for uid, unit in index.items()}
    titles = {source["id"]: _source_title(source) for source in sources}
    concepts = [_terms(value)[0] for value in _DOMAIN_CONCEPTS]
    frequency = Counter(token for words, _ in terms.values() for token in words)
    vocabulary = set(frequency).union(*titles.values())
    idf = {token: 1 + log((1 + len(index)) / (1 + frequency[token])) for token in vocabulary}
    kinds = {unit["kind"] for unit in index.values()}
    packets, details = {}, {}
    for group in GROUPS:
        _, rules = rubric._rule_cards(group, family, "rules")
        for sid in GROUP_SKILLS[family][group]:
            rule = rules[sid]
            linkage = rule["linkage_policy"]
            knowledge = linkage == "same_concept_independent_sources"
            allowed = {"claim", "listed"} if knowledge else {"claim"}
            profile = _profile(catalog[sid], rule, concepts)
            ranked = [
                (*_rank_activity(profile, source, allowed, parts, titles, idf), source["id"])
                for source in sources
                if any(unit["kind"] in allowed for unit in source["units"])
            ]
            ranked = sorted((entry for entry in ranked if entry[0] > 0), key=lambda entry: -entry[0])
            chosen = _shortlist(ranked, knowledge)
            picked = {activity_id for _, _, activity_id in chosen}
            in_order = [source for source in sources if source["id"] in picked]
            unit_ids = [unit["id"] for source in in_order for unit in source["units"]]
            eligible = [uid for uid in unit_ids if index[uid]["kind"] in allowed]
            omitted = [
                activity_id for score, direct, activity_id in ranked
                if activity_id not in picked and (direct or score >= ranked[0][0] * 0.25)
            ]
            if not allowed & kinds:
                state = "no_eligible_source_kind"
            elif not ranked:
                state = "no_action_or_lexical_match"
            elif omitted:
                state = "plausible_activities_not_selected"
            else:
                state = "selected_matches"
            packets[sid] = {
                "unit_ids": unit_ids,
                "criterion_unit_ids": {criterion: list(eligible) for criterion in rubric.CRITERION_IDS},
                "linkage_policy": linkage,
                "workload_id": f"automatic-v2-{sid}",
            }
            details[sid] = {
                "selected_activity_ids": [source["id"] for source in in_order],
                "eligible_unit_ids": eligible,
                "matched_activity_count": len(ranked),
                "top_activity_ranks": [
                    {"activity_id": a, "rank_score": round(s, 4), "core_action_match": d}
                    for s, d, a in ranked[:5]
                ],
                "omitted_plausible_activity_ids": omitted,
                "selection_state": state,
                "search_incomplete": state in {"no_action_or_lexical_match", "plausible_activities_not_selected"},
            }
    return {
        "version": rubric.PACKET_VERSION, "job_family": family,
        "source_sha256": rubric.sha(sources), "skills": packets,
    }, {
        "version": _RANKING_VERSION, "family": family, "source_activity_count": len(sources),
        "source_unit_count": len(index), "skills": details,
    }


_CRITERION_VERSION = "entry-level-criterion-activity.v1"

# These features nominate candidates. The Agent and scorer retain ownership,
# exact citation, practice, and workload checks.
_METADATA_CLAIM = re.compile(r"^\s*(?:advis[eo]r|supervisor|mentor|supervised by|mentored by)\b", re.I)
_TRAINING_MECHANISM = re.compile(
    r"\b(?:epochs?|learning rate|batch size|optimizer|loss function|dropout|hyperparameter(?:s| tuning)?|"
    r"warm[- ]?up|weight decay|scheduled learning|gradient accumulation|train(?:ing)? split|"
    r"training objective|training configuration|(?:training )?datasets?|training data|paramet(?:er|re)s?|model weights?)\b",
    re.I,
)
_TRAINING_OPERATION = re.compile(
    r"(?:^|[,;]\s*|\b(?:I|we)\s+|\band\s+)(?:personally\s+)?"
    r"(?:train(?:ed)?|fit(?:ted)?|fine[- ]?tuned|retrained|tuned|updated|optimized)\b",
    re.I,
)
_CHECK_ACTIONS = {"analyze", "check", "compare", "evaluate", "measure", "monitor", "reconcile", "review", "test"}
_EXECUTED_CHECK = re.compile(
    r"\b(?:analy[sz]ed|asserted|audited|benchmarked|checked|compared|confirmed|evaluated|examined|exercised|"
    r"inspected|measured|monitored|observed|reconciled|reviewed|tested|tracked|validated|verified)\b", re.I,
)
_CHECK_SCOPE = re.compile(
    r"\b(?:for|to|enabling|supporting|intended for|designed to|prepared for)\s+(?:later\s+|future\s+|downstream\s+|"
    r"repeatable\s+|automated\s+|controlled\s+)*(?:test(?:s|ing)?|check(?:s|ing)?|validat(?:e|ion|ing)|"
    r"evaluat(?:e|ion|ing)|compar(?:e|ison|ing)|benchmark(?:ing)?|experiments?|analysis)\b", re.I,
)
_METHOD_CUES = re.compile(
    r"\b(?:with|using|via|through|by|into|from|based on|configured|built|implemented)\b", re.I,
)
_OUTPUT_ARTIFACT = re.compile(
    r"\b(?:predictions?|(?:model|generated|structured)\s+outputs?|(?:model[- ]generated|structured)\s+JSON|model response(?:s)?|"
    r"(?:generated|model)\s+(?:answers?|text|responses?|content|captions?|transcripts?)|"
    r"(?:generated|returned)\s+(?:JSON|fields?|transcriptions?)|transcribed\s+(?:text|output))\b", re.I,
)
_CHECK_SUPPORT = re.compile(r"\b(?:validation layer|feedback[- ]driven validation|systematic evaluation)\b", re.I)
_SERVING_PROTOTYPE = re.compile(r"\b(?:built|developed|implemented)\b.+\b(?:real[- ]time|online)\b.+\bprototype\b", re.I)


def _training_pair(text):
    return any(_TRAINING_OPERATION.search(clause) and _TRAINING_MECHANISM.search(clause)
               for clause in _personal_clauses(text))


def _personal_clauses(text):
    # A project bullet may combine an attributed teammate action and the
    # applicant's own practice. Do not grant permission based on the former.
    parts = re.split(r"[.!?;](?:\s+|$)|,\s*(?:but\s+|while\s+)?(?=I\b)", text)
    return (clause for clause in parts if clause.strip() and not _THIRD_PARTY_SUBJECT.match(clause))


def _training_core(text):
    return any(_TRAINING_OPERATION.search(clause) or re.search(
        r"\b(?:conducted|ran|completed)\b.+\b(?:training|fine[- ]?tuning)\b", clause, re.I,
    ) for clause in _personal_clauses(text))


def _observed_check(text):
    for clause in _personal_clauses(text):
        # A separate finite check verb can be explicit even if the same line
        # also describes a preparatory purpose or a different intended check.
        for event in _EXECUTED_CHECK.finditer(clause):
            if not _CHECK_SCOPE.search(clause[:event.start()]):
                return True
    return False


def _candidate(unit, criterion, rule, profile):
    text = unit["text"]
    if _METADATA_CLAIM.match(text):
        return False
    weights, _, concepts, core_actions = profile
    # Keep affirmative and ambiguous evidence for the Agent; a named third
    # party alone does not create a positive core or an activity's child scope.
    words, actions = _terms(text)
    relevant = bool(words & concepts or words & weights.keys() or actions & core_actions)
    if rule["skill_id"] == "model_training":
        if criterion == "c1":
            return _training_core(text)
        if criterion == "c2":
            return _training_core(text) or bool(_TRAINING_MECHANISM.search(text))
        return _observed_check(text)
    if criterion == "c1":
        return relevant or (rule["skill_id"] == "model_deployment" and bool(_SERVING_PROTOTYPE.search(text)))
    if criterion == "c2":
        return relevant or bool(_METHOD_CUES.search(text))
    if rule["c3_kind"] != "executed_check":
        return relevant or bool(actions & _CHECK_ACTIONS) or bool(_EXECUTED_CHECK.search(text))

    # LLM check proof must be a possible model artifact. Prospective check
    # text and comparison targets stay available as surrounding context.
    observed_check = _observed_check(text)
    if rule["skill_id"] == "llm":
        checked = re.split(r"\bagainst\b|\bcompared (?:with|to)\b", text, maxsplit=1, flags=re.I)[0]
        return observed_check and bool(_OUTPUT_ARTIFACT.search(checked))
    return observed_check or bool(_CHECK_SUPPORT.search(text))


def _select_activities(sid, current, ranks, by_activity):
    if sid != "model_training":
        return list(current), False
    # When lexical ranking misses an explicit core+method example, reserve one
    # of the existing slots for it. Keep the strongest other activities.
    direct = [
        row["activity_id"] for row in ranks
        if any(unit["kind"] == "claim" and _training_pair(unit["text"])
               for unit in by_activity[row["activity_id"]]["units"])
    ]
    selected = (direct + [activity for activity in current if activity not in direct])[:3]
    return selected, set(selected) != set(current)


def _select_criteria(base_input):
    """Return a validator-compatible packet and per-activity permission audit."""
    packet, diagnostics = _select_activity_candidates(base_input)
    family = base_input["job_family"]
    sources = base_input["resume_sources"]
    by_activity = {source["id"]: source for source in sources}
    index = build_index(sources)
    catalog = rubric._catalog(family)
    concepts = [_terms(concept)[0] for concept in _DOMAIN_CONCEPTS]
    for group in GROUPS:
        _, rules = rubric._rule_cards(group, family, "rules")
        for sid in GROUP_SKILLS[family][group]:
            rule = rules[sid]
            item, detail = packet["skills"][sid], diagnostics["skills"][sid]
            knowledge = item["linkage_policy"] == "same_concept_independent_sources"
            kinds = {"claim", "listed"} if knowledge else {"claim"}
            profile = _profile(catalog[sid], rule, concepts)
            selected, reserved = _select_activities(sid, detail["selected_activity_ids"],
                                                     detail["top_activity_ranks"], by_activity)
            activity_candidates = {}
            selected_set = set(selected)
            retained = [source for source in sources if source["id"] in selected_set]
            eligible = {unit["id"] for source in retained for unit in source["units"] if unit["kind"] in kinds}
            for source in retained:
                units = [unit for unit in source["units"] if unit["id"] in eligible]
                c1 = [u["id"] for u in units if _candidate(u, "c1", rule, profile)]
                possible_practice = knowledge or any(
                    any(not third_party for _, _, third_party in _claim_parts(index[uid]["text"]))
                    for uid in c1
                )
                activity_candidates[source["id"]] = {
                    "c1": c1,
                    **{cid: [u["id"] for u in units if possible_practice and _candidate(u, cid, rule, profile)]
                       for cid in ("c2", "c3")},
                }
            permissions = {cid: [uid for rows in activity_candidates.values() for uid in rows[cid]]
                           for cid in rubric.CRITERION_IDS}
            item.update(unit_ids=[u["id"] for source in retained for u in source["units"]],
                        criterion_unit_ids=permissions, workload_id=f"automatic-criteria-{sid}")
            detail.update(selected_activity_ids=[source["id"] for source in retained],
                          eligible_unit_ids=[uid for uid in index if uid in eligible],
                          criterion_unit_ids_by_activity=activity_candidates,
                          reserved_core_and_method_activity=reserved)
            # If a matched scope lost all core candidates during narrowing,
            # preserve the existing selector abstention behavior.
            if eligible and not permissions["c1"]:
                detail.update(search_incomplete=True, selection_state="no_core_candidate_after_narrowing")
            if reserved:
                omitted = set(detail["omitted_plausible_activity_ids"]) | {
                    activity for activity in by_activity if activity in {
                        row["activity_id"] for row in detail["top_activity_ranks"] if row["core_action_match"]
                    }
                }
                detail["omitted_plausible_activity_ids"] = sorted(omitted - selected_set)
                detail["search_incomplete"] = bool(detail["omitted_plausible_activity_ids"])
                detail["selection_state"] = (
                    "plausible_activities_not_selected" if detail["search_incomplete"] else "selected_matches"
                )
    diagnostics["version"] = _CRITERION_VERSION
    return packet, diagnostics


SELECTOR_VERSION = "entry-level-criterion-activity-recall.v1"
MAX_ACTIVITIES = 3
_FUTURE_OR_NEGATED = re.compile(
    r"\b(?:plan(?:ned|s)? to|planning to|intend(?:ed|s)? to|prepared to|will|would|"
    r"not|never|future|upcoming|yet to|next (?:week|month|term|quarter))\b", re.I,
)
_OTHER_OWNER = re.compile(
    r"\b(?:we|(?:my|our|the|a|another) (?:team|teammates?|colleagues?|"
    r"coworkers?|co-workers?|supervisors?|partner|manager)|someone else)\b", re.I,
)
_CADENCE = re.compile(
    r"\b(?:nightly|daily|weekly|hourly|monthly|recurring|repeatable|scheduled|"
    r"automated|automatically|on a schedule|cron|whenever|"
    r"(?:every|each) (?:night|evening|morning|day|week|hour|month|run|batch))\b", re.I,
)
_READ_STAGE = re.compile(
    r"\b(?:open(?:ed|s)?|read(?:s)?|ingest(?:ed|s)?|pull(?:ed|s)?|"
    r"fetch(?:ed|es)?|extract(?:ed|s)?|collect(?:ed|s)?|import(?:ed|s)?|"
    r"load(?:ed|s)?|download(?:ed|s)?)\s+(?!to\b|into\b)\w+", re.I,
)
_WRITE_STAGE = re.compile(
    r"\b(?:wrote|write(?:s)?|append(?:ed|s)?|load(?:ed|s)?|upload(?:ed|s)?|"
    r"export(?:ed|s)?|sav(?:ed|es)|stor(?:ed|es)|publish(?:ed|es)?|"
    r"sent|send(?:s)?|cop(?:ied|ies|y)|moved|moves|stream(?:ed|s)?)\b"
    r"(?:\s+[^,.;!?]+?)?\s+(?:to|into|in|under|as|on)\s+\w+", re.I,
)
_TRANSFER = re.compile(
    r"\b(?:cop(?:ied|ies|y)|moved|moves|transfer(?:red|s)?|import(?:ed|s)?|"
    r"load(?:ed|s)?|sync(?:ed|s)?|stream(?:ed|s)?)\s+[^,.;!?]+?"
    r"\s+from\s+[^,.;!?]+?\s+(?:to|into)\s+\w+", re.I,
)
_DIRECT_PRACTICE = re.compile(
    r"(?:^|,\s*)\s*(?:built|wrote|created|developed|implemented|configured|"
    r"operated|ran|maintained|set up|automated|scheduled|ingested|loaded|read|"
    r"opened|pulled|fetched|extracted|imported)\b", re.I,
)
_ONCE = re.compile(r"\b(?:one[- ]off|one[- ]time|once|single[- ]run)\b(?!\s+(?:a|per)\b)", re.I)

_MODEL_ARTIFACT = re.compile(
    r"\b(?:generated\s+(?:llm|language[- ]model|chatbot|assistant)\s+"
    r"|(?:llm|language[- ]model|chatbot|assistant|model)[- ]generated\s+"
    r"|(?:llm|language[- ]model|chatbot|assistant)(?:'s)?\s+)"
    r"(?:[\w-]+\s+){0,2}(?:answers?|responses?|outputs?|summar(?:y|ies)|"
    r"captions?|transcripts?|text|json)\b"
    r"|\b(?:answers?|responses?|outputs?)\s+generated\s+by\s+(?:the\s+)?"
    r"(?:llm|language[- ]model|chatbot|assistant)\b", re.I,
)
_COMPARATOR = re.compile(
    r"\b(?:against|versus|vs\.?|relative to|compared (?:with|to)|alongside)\b", re.I,
)
_REFERENCE = re.compile(
    r"\b(?:reference|expected|benchmark|control|ground[- ]truth|baseline)\s+"
    r"(?:[\w-]+\s+){0,2}(?:answers?|responses?|outputs?|summar(?:y|ies)|"
    r"captions?|transcripts?|text|json)\b", re.I,
)
_MODEL_USE = re.compile(
    r"\b(?:used|applied|called|invoked|ran|integrated|built|implemented|developed|"
    r"configured|prompted|deployed|routed|sent|passed)\b.{0,175}\b"
    r"(?:llm|language[- ]model|llama|gpt[-\w]*|claude|gemini|chatbot)\b", re.I,
)
_PROPOSED_CHECK = re.compile(r"\b(?:prepared|planned|proposed|designed)\b", re.I)


def _workflow_core(text):
    """Nominate a clearly repeated, personally operated source-to-output flow."""
    for clause in _personal_clauses(text):
        if (_FUTURE_OR_NEGATED.search(clause) or _OTHER_OWNER.search(clause) or _ONCE.search(clause)
                or not _CADENCE.search(clause)):
            continue
        if not re.search(r"\b(?:I|my)\b", clause, re.I) and not _DIRECT_PRACTICE.search(clause):
            continue
        first_stage = _READ_STAGE.search(clause)
        if _TRANSFER.search(clause) or (first_stage and _WRITE_STAGE.search(clause, first_stage.end())):
            return True
    return False


def _checked_model_output(text):
    """Nominate an actually checked model artifact in its governing clause."""
    for clause in _personal_clauses(text):
        if _OTHER_OWNER.search(clause):
            continue
        for event in _EXECUTED_CHECK.finditer(clause):
            lead = clause[:event.start()]
            if (_CHECK_SCOPE.search(lead) or _FUTURE_OR_NEGATED.search(lead)
                    or _PROPOSED_CHECK.search(lead)):
                continue
            checked = _COMPARATOR.split(clause[event.end():], maxsplit=1)[0]
            if _MODEL_ARTIFACT.search(checked) and not _REFERENCE.search(checked):
                return True
    return False


def _matches(source, predicate):
    return [unit["id"] for unit in source["units"]
            if unit["kind"] == "claim" and predicate(unit["text"])]


def _update_permissions(item, detail, sources):
    approved = detail["criterion_unit_ids_by_activity"]
    chosen = [source for source in sources if source["id"] in approved]
    detail["selected_activity_ids"] = [source["id"] for source in chosen]
    detail["eligible_unit_ids"] = [unit["id"] for source in chosen for unit in source["units"]
                                   if unit["kind"] == "claim"]
    item["unit_ids"] = [unit["id"] for source in chosen for unit in source["units"]]
    item["criterion_unit_ids"] = {
        cid: [uid for source in chosen for uid in approved[source["id"]][cid]]
        for cid in item["criterion_unit_ids"]
    }


def _extend_permission(approvals, cid, candidates, source):
    allowed = set(approvals[cid]).union(candidates)
    approvals[cid] = [unit["id"] for unit in source["units"] if unit["id"] in allowed]


def _recover_pipelines(item, detail, sources):
    approved = detail["criterion_unit_ids_by_activity"]
    direct = {source["id"]: _matches(source, _workflow_core) for source in sources}
    direct = {aid: ids for aid, ids in direct.items() if ids}
    # Reserve at most one open slot, retaining the previously selected projects.
    addition = next((aid for aid in direct if aid not in approved), None)
    if addition and len(approved) < MAX_ACTIVITIES:
        approved[addition] = {"c1": [], "c2": [], "c3": []}
    for source in sources:
        aid = source["id"]
        if aid in approved and aid in direct:
            _extend_permission(approved[aid], "c1", direct[aid], source)
    omitted = set(detail["omitted_plausible_activity_ids"]).union(direct) - approved.keys()
    if omitted:
        detail.update(omitted_plausible_activity_ids=sorted(omitted), search_incomplete=True,
                      selection_state="plausible_activities_not_selected")
    elif direct:
        detail.update(omitted_plausible_activity_ids=[], search_incomplete=False,
                      selection_state="selected_matches")
    _update_permissions(item, detail, sources)


def _recover_llm(item, detail, sources):
    approved = detail["criterion_unit_ids_by_activity"]
    for source in sources:
        activity = approved.get(source["id"])
        if activity and any(
            unit["id"] in activity["c1"] and any(
                not _OTHER_OWNER.search(clause) and not _FUTURE_OR_NEGATED.search(clause)
                and _MODEL_USE.search(clause)
                for clause in _personal_clauses(unit["text"])
            )
            for unit in source["units"]
        ):
            _extend_permission(activity, "c3", _matches(source, _checked_model_output), source)
    _update_permissions(item, detail, sources)


def select(base_input):
    """Return the same packet contract, with focused pipeline and LLM recall."""
    packet, diagnostics = _select_criteria(base_input)
    sources = base_input["resume_sources"]
    for skill, recover in (("data_pipelines", _recover_pipelines), ("llm", _recover_llm)):
        if skill in packet["skills"]:
            recover(packet["skills"][skill], diagnostics["skills"][skill], sources)
    diagnostics["version"] = SELECTOR_VERSION
    return packet, diagnostics
