# Original and updated entry three-Agent comparison

Both arms completed a fresh three-Agent run on the same confirmed AI Engineer resume. Each arm ran its three groups in parallel. The original arm used Foundation v2, Lifecycle v2 and Systems v2. The entry arm used Foundation v3, Lifecycle v4 and Systems v7. The job-family scope remained 23 skills and all 566 AI Engineer jobs in the demand snapshot.

| Measure | Original | Updated entry |
| --- | ---: | ---: |
| Group wall time through local scoring, seconds | 40.15 | 41.67 |
| Wall time with measured assembly and preflight, seconds | 41.23 | 41.68 |
| Weighted score over each arm's scored skills | 44.46% | 66.18% |
| Weighted score over the same 17 scored skills | 44.20% | 67.35% |
| Scored skills | 19/23 | 19/23 |
| Pending skills | 4/23 | 4/23 |
| Demand weight represented by scored skills | 92.22% | 91.79% |

The common 17 skills represent 89.31% of total skill demand weight. The common-cohort difference is 23.15 percentage points. The original rubric scores evidence strength from the application, method and validation evidence. The entry rubric scores coverage of entry-level criteria. The original groups receive the full resume source representation and the entry groups receive their fixed evidence packets. Both workflow differences affect the scores.

| Inference time, seconds | Original | Updated entry |
| --- | ---: | ---: |
| Foundation | 32.05 | 39.55 |
| Lifecycle | 30.75 | 22.68 |
| Systems | 38.98 | 33.26 |

Lifecycle and Systems completed inference sooner in the entry arm. Foundation became its longest call, so entry group wall time through scoring was 1.51 seconds longer. With measured preparation and preflight, the difference was 0.45 seconds. The timing excludes previous resume parsing and reviewer evidence selection. This is one paired observation.

| Skill | Original score and grade | Updated entry score and grade |
| --- | --- | --- |
| General programming | 20 (D) | 0 (F) |
| Python development | 20 (D) | 80 (A-) |
| Software engineering | 60 (B) | 100 (A) |
| SQL | 20 (D) | 0 (F) |
| Machine learning | 50 (C) | 90 (A) |
| Deep learning | 50 (C) | 70 (B+) |
| Mathematics and statistics | 50 (C) | 90 (A) |
| Data preparation | 60 (B) | 65 (B) |
| Data pipelines | 60 (B) | 80 (A-) |
| Feature engineering | 60 (B) | 80 (A-) |
| Model training | 55 (C) | 80 (A-) |
| Fine-tuning | 50 (C) | Pending |
| Model evaluation | 60 (B) | 80 (A-) |
| Experimentation | 50 (C) | 80 (A-) |
| Model deployment and serving | Pending | Pending |
| MLOps | 45 (C) | 80 (A-) |
| AI infrastructure | 50 (C) | 0 (F) |
| Generative AI | 50 (C) | 100 (A) |
| Large language models | 45 (C) | 80 (A-) |
| Retrieval-augmented generation | 60 (B) | Pending |
| Agents and tool use | Pending | Pending |
| Prompt engineering | Pending | 50 (C) |
| Vector representations and retrieval | Pending | 0 (F) |

Original pending skills were Model Deployment, AI Agents, Prompt Engineering and Vector Retrieval. Entry pending skills were Fine-tuning, Model Deployment, RAG and AI Agents. All three entry group-level validations passed. Lifecycle scored six of eight skills and retained both target facts as performed personal work. Fine-tuning lacked explicit pretrained-origin and parameter-update evidence, and Deployment lacked an explicit runnable serving path. Their dependent judgments stayed unassessed. The earlier Lifecycle group-wide validation failure did not recur in this pair.

All six calls completed. The inventory and 1,329 frozen file checks passed. This comparison used existing Agent definitions and the original application path for the original arm. It made zero Agent mutations and did not use the database, commit or push. `results.json` contains all metrics and skill rows. Raw resume evidence and outputs remain in the ignored local run directory.
