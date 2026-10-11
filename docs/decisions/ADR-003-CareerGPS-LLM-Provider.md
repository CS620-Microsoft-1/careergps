# ADR-003: LLM Provider for CareerGPS

- **Status:** Pending Approval
- **Date:** 2026-10-10
- **Decision Owners:** CareerGPS Development Team
- **Project:** CareerGPS
- **Scope:** Large language model (LLM) provider used by the backend

---

## 1. Context

ADR-002 selected Python, FastAPI, Pydantic and SQLAlchemy for the backend and explicitly left the LLM provider to a separate ADR.

The first feature that needs an LLM is résumé parsing ([SPEC-001](../specs/SPEC-001-signup-to-dashboard.md)):

```text
PDF → pdfplumber → résumé text → LLM → JSON (ResumeExtraction) → user confirms
```

The LLM must turn free-form résumé text into a fixed JSON structure (contact, education, experience, projects, skills). Later features (skill gaps, job-description structuring, recommendations, agent workflows) will use the same provider.

Résumé text is personal data. Whatever provider we choose receives it.

---

## 2. Decision Drivers

- **Reliable structured output:** responses must follow a JSON schema we define, so they can be validated with Pydantic.
- **Data handling:** clear terms on whether prompts are stored or used for training.
- **Fit with the project:** CareerGPS is a Microsoft-sponsored project.
- **Cost:** a student team budget; résumé parsing runs once per upload.
- **Python support:** an official, maintained Python SDK.
- **Replaceability:** we should be able to switch provider without rewriting features.

---

## 3. Decision

CareerGPS will use **Azure OpenAI** as its LLM provider.

All LLM calls go through one backend interface, `LLMClient`, so that features never import the provider SDK directly:

```text
Feature code (e.g. résumé parsing)
        ↓
     LLMClient          ← the only place that knows about Azure OpenAI
        ↓
   Azure OpenAI
```

The specific model deployment is **not** fixed by this ADR. It is chosen during implementation (see §8), with one hard requirement: the model must support structured outputs with a JSON schema.

---

## 4. Rationale

### 4.1 Structured outputs

Résumé parsing only works if the LLM returns valid JSON in our schema. Azure OpenAI offers structured outputs: the request includes a JSON schema and the model's response is constrained to it. We still validate every response with Pydantic (SPEC-001 §7.3), but schema-constrained output makes validation failures rare instead of routine.

### 4.2 Data handling

Microsoft's documentation for Azure OpenAI states that prompts and completions are not used to train the models and are not shared with OpenAI. This matters because we send résumés. The exact retention terms (for example, abuse-monitoring storage) must be checked against Microsoft's current documentation when the resource is set up and reflected in our privacy policy.

### 4.3 Fit with the project

The project is sponsored by Microsoft. Using Azure OpenAI keeps the AI part of the stack in the sponsor's ecosystem and makes it easier to get help, credits or access through the sponsor if needed.

### 4.4 Python ecosystem

Azure OpenAI is supported by the official `openai` Python SDK, which works naturally with Pydantic models and async FastAPI code.

---

## 5. Alternatives Considered

### 5.1 OpenAI API (directly)

- **Advantages:** same model family; often the earliest access to new models; simplest setup.
- **Disadvantages:** outside the sponsor's ecosystem; separate data-handling terms to review.
- **Why not selected:** Azure OpenAI gives the same models with a better fit for this project. Because the `openai` SDK serves both, switching later is cheap.

### 5.2 Anthropic Claude API

- **Advantages:** strong long-document understanding and instruction following; supports schema-constrained tool/JSON output; official Python SDK.
- **Disadvantages:** not part of the sponsor's ecosystem; a second vendor relationship to manage.
- **Why not selected:** project fit. It remains a good fallback behind `LLMClient`.

### 5.3 Google Gemini API

- **Advantages:** supports schema-constrained JSON output; large context windows; low-cost small models.
- **Disadvantages:** not part of the sponsor's ecosystem.
- **Why not selected:** project fit.

### 5.4 Self-hosted open-weight model

- **Advantages:** résumés never leave our infrastructure; no per-call fees.
- **Disadvantages:** needs GPU hosting and operations work the team does not have time for; structured-output reliability depends on extra tooling; quality on messy résumés is likely lower.
- **Why not selected:** too much operational work for a student team at this stage.

---

## 6. Consequences

### Positive

- Schema-constrained output for résumé parsing and future structured features
- Clear data-handling terms suitable for personal data
- Aligned with the project sponsor
- Provider can be swapped behind `LLMClient`

### Negative and trade-offs

- **Azure setup overhead:** an Azure subscription, an Azure OpenAI resource, and a model deployment are required before any code can call the model.
- **Deployment names, not model names:** Azure calls a *deployment* the team creates, so the deployment name must be configured per environment.
- **Regional model availability:** not every model is available in every Azure region; the region must be chosen with this in mind.
- **Cost exists per call:** usage must be watched, especially once agent workflows make several calls per request.

---

## 7. Implementation Guidelines

1. Create one Azure OpenAI resource for the team and a model deployment that supports structured outputs.
2. Configuration lives in backend `.env` only and is added to `.env.example` as placeholders:
   ```text
   AZURE_OPENAI_ENDPOINT=https://<resource-name>.openai.azure.com/
   AZURE_OPENAI_API_KEY=<key>
   AZURE_OPENAI_DEPLOYMENT=<deployment-name>
   AZURE_OPENAI_API_VERSION=<api-version>
   ```
   The key is never committed, logged, pasted into chat, or sent to the frontend. If it leaks, rotate it in the Azure portal.
3. Implement `LLMClient` in `backend/app/services/llm.py`. Feature code depends on `LLMClient`, never on the SDK.
4. Every structured call passes a Pydantic model; the response is validated with that model. On a validation error, retry once with the errors in the prompt, then fail (SPEC-001 §7.3).
5. Set a request timeout and treat provider errors as `llm_unavailable` (SPEC-001 §6).
6. Treat document text as untrusted data: wrap it as data in the prompt and tell the model to ignore instructions inside it.
7. Never log prompts or responses that contain résumé content. Log only metadata (latency, token counts, status).
8. Tests never call the real API. `LLMClient` is faked in unit and API tests; the parser-quality set (SPEC-001 §11) runs manually.

---

## 8. Open Items

| Item | How it will be settled |
|---|---|
| Model deployment | Compare 1–2 candidate models that support structured outputs on the parser-quality sample résumés; pick on accuracy, latency and cost. Record the choice here. |
| Azure subscription and credits | Confirm who owns the Azure resource and whether sponsor or student credits cover it. |
| Region | Pick a region where the chosen model is available. |
| Data retention terms | Check Microsoft's current Azure OpenAI data-privacy documentation; update the privacy policy shown at sign-up. |

---

## 9. Final Decision Summary

CareerGPS will use **Azure OpenAI** as its LLM provider, accessed only through a backend `LLMClient` interface. The main reasons are reliable schema-constrained output for résumé parsing, clear data-handling terms for personal data, and fit with the Microsoft-sponsored project. The specific model deployment will be selected by testing on sample résumés and recorded in this ADR.
