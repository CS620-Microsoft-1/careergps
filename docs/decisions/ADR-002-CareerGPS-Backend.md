# ADR-002: Backend Technology Stack for CareerGPS

- **Status:** Pending Approval
- **Date:** 2026-10-07
- **Decision Owners:** CareerGPS Development Team
- **Project:** CareerGPS
- **Scope:** Backend Programming Language and API Framework

---

## 1. Context

CareerGPS requires a backend that can support the application logic behind student career analysis, résumé processing, skill analysis, market intelligence, recommendations, and future AI-agent workflows.

The backend will sit between the Next.js frontend and the internal application logic.

At a high level, the backend must be able to:

- Receive requests from the frontend
- Validate structured input
- Execute CareerGPS application logic
- Support future AI and agent-related processing
- Return structured responses
- Integrate cleanly with external AI services and internal application components
- Maintain a clear separation between the API layer and the underlying business logic
- Support clean access to future structured relational data

The Microsoft project description specifically emphasizes full-stack engineering, AI/ML systems, multi-agent systems, information retrieval, evaluation, observability, security, and distributed-system concepts. It also explicitly lists Python and FastAPI as suitable implementation technologies.

The purpose of this ADR is primarily to decide:

- The backend programming language
- The backend API framework
- The preferred Python-side database access approach

The specific database technology, vector storage, agent orchestration framework, caching system, model provider, and observability tools will be decided separately.

---

## 2. Decision Drivers

The main factors influencing the backend technology decision are:

- Strong support for AI-oriented development
- Strong ecosystem for document processing and data analysis
- Ease of integration with LLM and embedding APIs
- Ability to support future agent workflows
- Clear and maintainable API development
- Structured request and response validation
- Good integration with the TypeScript/Next.js frontend
- Strong developer productivity
- Low unnecessary framework complexity
- Async support for network-heavy AI workloads
- Automatic API documentation
- Readability for a multi-developer student team
- Flexibility to evolve the internal architecture later
- Clean interaction with future relational database systems

---

## 3. Decision

CareerGPS will use:

| Technology       | Role                                                                            |
| ---------------- | ------------------------------------------------------------------------------- |
| **Python 3.12+** | Primary backend programming language                                            |
| **FastAPI**      | Backend API framework                                                           |
| **Pydantic**     | Request, response, and structured data validation within the FastAPI layer      |
| **SQLAlchemy**   | Preferred Python database access toolkit and ORM for structured relational data |

The backend will communicate with the Next.js frontend through HTTP APIs and potentially streaming mechanisms where needed.

The initial high-level architecture will be:

```text
Next.js Frontend
       |
       | HTTP / API
       v
    FastAPI
       |
       v
     Python
       |
       +------> SQLAlchemy
       |           |
       |           v
       |     Relational Database
       |
       v
CareerGPS Application Logic
```

FastAPI will serve as the communication boundary between the frontend and backend application logic.

Python will be used to implement the backend logic that supports CareerGPS functionality.

SQLAlchemy may be used as the Python-side abstraction for interacting with structured relational databases.

The specific database engine will be decided in a separate database ADR.

---

## 4. Technology Decisions and Rationale

### 4.1 Python

#### Purpose

Python will be the primary programming language for the CareerGPS backend.

It will be used to implement:

- Career analysis logic
- Résumé-processing logic
- Data transformations
- AI service integrations
- Future agent-related workflows
- Evaluation and analysis utilities
- Backend service logic

#### Why We Selected It

CareerGPS is not expected to be a simple CRUD-only application.

Its backend will eventually need to support AI-heavy and data-heavy workflows such as:

```text
Resume processing

Document processing

LLM interaction

Embeddings

Retrieval

Career-market analysis

Evaluation

Structured AI outputs

Agent workflows
```

Python has one of the strongest ecosystems for these types of workloads.

The language has mature support for libraries and frameworks commonly used in:

- Machine learning
- Natural language processing
- Data processing
- AI systems
- Retrieval systems
- Evaluation
- Model APIs

Examples of relevant Python ecosystem technologies include:

```text
Pydantic
FastAPI
SQLAlchemy
PyTorch
Transformers
SentenceTransformers
scikit-learn
pandas
NumPy
LangGraph
LangChain
```

CareerGPS may not use all of these technologies, but selecting Python gives the project access to a mature ecosystem as requirements evolve.

#### Project-Specific Benefits

CareerGPS will likely combine two types of backend work:

```text
AI-based reasoning
+
deterministic application logic
```

For example, a future market-analysis workflow may involve:

```text
Retrieve relevant jobs
       ↓
Calculate skill frequencies
       ↓
Compare student skills
       ↓
Generate structured findings
       ↓
Use AI to explain the findings
```

Not every operation should be delegated to an LLM.

Python is well suited for combining:

- Normal algorithms
- Data processing
- Statistical analysis
- AI models
- External AI APIs

This allows CareerGPS to keep deterministic work deterministic while using LLMs only where reasoning or synthesis is useful.

#### Future Agent Compatibility

Choosing Python does not restrict the future agent architecture.

The orchestration layer can later be implemented behind the API layer using a Python-compatible framework or custom orchestration logic.

Conceptually:

```text
FastAPI
   ↓
CareerGPS Application Layer
   ↓
Future Orchestrator
   ↓
Specialized Agents
```

The specific orchestration framework is intentionally not selected in this ADR.

Python provides a strong environment for building agents because it supports both:

- AI reasoning workflows
- Standard application and data-processing logic

This is particularly useful for CareerGPS, where future agents will likely need to interact with structured student data, career-market information, retrieval systems, and deterministic analysis.

---

### 4.2 FastAPI

#### Purpose

FastAPI will be the API framework used to expose CareerGPS backend capabilities to the Next.js frontend.

FastAPI will primarily be responsible for:

- Receiving HTTP requests
- Routing requests to backend functionality
- Validating request data
- Returning structured responses
- Defining API contracts
- Handling API errors
- Supporting asynchronous operations
- Generating API documentation

FastAPI will not contain all CareerGPS business logic directly.

It will act primarily as the external interface to the backend.

#### Why We Selected It

CareerGPS already uses a separate Next.js frontend.

Therefore, the Python backend does not need to render the user interface.

Its primary job is to provide an API that the frontend can call.

The architecture is therefore naturally API-first:

```text
Next.js
   ↓
FastAPI
   ↓
CareerGPS Backend Logic
```

FastAPI is designed specifically for this type of architecture.

---

### 4.3 Pydantic for Structured Request and Response Validation

CareerGPS will exchange structured information frequently.

For example, the frontend may send:

```json
{
  "student_id": 123,
  "target_role": "AI Engineer"
}
```

FastAPI can define the expected structure using Pydantic:

```python
class CareerAnalysisRequest(BaseModel):
    student_id: int
    target_role: str
```

The backend can also return structured objects:

```python
class SkillGap(BaseModel):
    skill: str
    student_level: str
    market_frequency: float
    priority: str
```

This improves reliability because incorrect or incomplete data can be caught at the API boundary instead of propagating deep into the backend.

Structured responses are particularly important for CareerGPS because the system will eventually produce outputs such as:

- Student profiles
- Market requirement profiles
- Skill gaps
- Opportunity matches
- Recommendations
- Roadmaps
- Evidence and citations

---

### 4.4 SQLAlchemy

#### Purpose

SQLAlchemy will be the preferred Python toolkit for interacting with future structured relational database systems.

It provides both:

- A SQL toolkit
- An ORM, or Object-Relational Mapping layer

This allows Python code to interact with relational data without requiring raw SQL to be written throughout the backend.

#### Why We Selected It

CareerGPS will likely contain structured entities such as:

```text
Student
Resume
Skill
Job
Company
MarketProfile
SkillGap
Roadmap
```

These entities naturally map to relational database tables.

Instead of writing raw SQL everywhere:

```sql
SELECT *
FROM student_profiles
WHERE student_id = 123;
```

SQLAlchemy allows the backend to work with Python models and queries.

Conceptually:

```python
profile = session.query(StudentProfile).filter(
    StudentProfile.student_id == 123
).first()
```

SQLAlchemy then translates that Python-side query into SQL for the underlying relational database.

#### Project-Specific Benefits

Using SQLAlchemy keeps database interaction consistent with the rest of the Python backend.

The architecture becomes:

```text
FastAPI
   ↓
Python Services
   ↓
SQLAlchemy
   ↓
Relational Database
```

This provides several benefits:

- Cleaner separation between application logic and database queries
- Easier mapping between Python objects and relational tables
- Less duplicated raw SQL throughout the codebase
- Easier maintainability as the schema grows
- Ability to still use raw SQL when necessary

SQLAlchemy does not replace SQL or the database itself.

It is the Python-side access layer used to communicate with the structured database.

#### Important Scope Note

The use of SQLAlchemy does not decide which database CareerGPS will use.

For example, SQLAlchemy can work with relational databases such as:

```text
PostgreSQL
MySQL
SQLite
```

The specific database engine and schema design should be documented in a separate database ADR.

---

## 5. Alternatives Considered

### 5.1 TypeScript + Node.js

#### Why It Was Considered

The frontend already uses TypeScript, so using TypeScript on the backend would allow the entire application to use one programming language.

Possible backend frameworks could include:

- Express
- NestJS
- Fastify

#### Advantages

- One language across frontend and backend
- Easier context switching
- Potential type sharing
- Large ecosystem
- Strong async support
- Very mature web-development tooling

#### Disadvantages for CareerGPS

CareerGPS is expected to become significantly AI- and data-oriented.

Its future backend may need to support:

- Document processing
- AI evaluation
- Embeddings
- Retrieval
- Data analysis
- AI-agent workflows
- Machine-learning tooling

Python has a stronger and more mature ecosystem for these types of workloads.

Using TypeScript everywhere would reduce language switching, but it would provide less benefit in the area where CareerGPS is expected to become most technically complex.

#### Why It Was Not Selected

The team is prioritizing ecosystem fit for the AI-oriented backend over using a single language across the full stack.

**Decision:** Python selected over TypeScript/Node.js.

---

### 5.2 Java + Spring Boot

#### Why It Was Considered

Java and Spring Boot are widely used for large-scale enterprise backend applications.

#### Advantages

- Mature enterprise ecosystem
- Strong type safety
- Strong concurrency support
- Excellent tooling
- Highly structured architecture
- Strong performance

#### Disadvantages for CareerGPS

Spring Boot introduces more framework structure and boilerplate than CareerGPS currently requires.

CareerGPS's primary backend challenge is expected to involve:

- AI
- Document processing
- Analysis
- Retrieval
- Model integration

rather than extremely large-scale enterprise transaction processing.

The Python AI ecosystem also provides easier access to many of the tools the project may need later.

#### Why It Was Not Selected

Java would be capable of implementing CareerGPS, but Python provides faster development and a stronger ecosystem for the project's AI-oriented requirements.

**Decision:** Python selected over Java.

---

### 5.3 Go

#### Why It Was Considered

Go is commonly used for cloud infrastructure, networking, distributed systems, and high-performance APIs.

#### Advantages

- High performance
- Strong concurrency model
- Simple language
- Good deployment characteristics
- Strong cloud-native ecosystem

#### Disadvantages for CareerGPS

CareerGPS's most difficult backend requirements are not expected to involve extremely high request throughput.

The primary challenges are more likely to involve:

- AI integration
- Document analysis
- Retrieval
- Evaluation
- Structured AI workflows

Python provides significantly broader tooling for these areas.

#### Why It Was Not Selected

The performance advantages of Go do not provide enough benefit to outweigh Python's stronger AI and data-processing ecosystem.

**Decision:** Python selected over Go.

---

### 5.4 Flask

#### Why It Was Considered

Flask is a mature and lightweight Python web framework.

It could successfully expose the CareerGPS backend through APIs.

#### Advantages

- Simple
- Mature
- Flexible
- Large community
- Easy to learn

#### Disadvantages for CareerGPS

Flask is intentionally minimal.

Features such as:

- Structured request validation
- Structured response models
- Automatic OpenAPI documentation
- Strong type-oriented API contracts

require more manual setup or additional libraries.

CareerGPS is expected to exchange many structured objects between the frontend and backend.

FastAPI provides these capabilities more naturally.

#### Why It Was Not Selected

FastAPI offers a stronger API-first development experience while remaining lightweight.

Its integration with Pydantic and automatic API documentation make it a better fit for CareerGPS.

**Decision:** FastAPI selected over Flask.

---

### 5.5 Django

#### Why It Was Considered

Django is a mature Python framework for building complete web applications.

#### Advantages

- Mature ecosystem
- Built-in authentication
- Built-in ORM
- Admin interface
- Strong conventions
- Suitable for large web applications

#### Disadvantages for CareerGPS

Django includes many full-stack features that CareerGPS does not need from its Python backend.

The frontend is already being built separately using Next.js.

Therefore, the backend does not need:

- Django templates
- Server-rendered HTML
- Django's full traditional web stack

The project primarily needs an API layer around Python application logic.

#### Why It Was Not Selected

FastAPI is more focused on the API-first architecture CareerGPS requires and introduces less unnecessary framework complexity.

**Decision:** FastAPI selected over Django.

---

## 6. Backend Architecture Overview

The backend will initially be structured conceptually as:

```text
                 Next.js Frontend
                        |
                        |
                     HTTP/API
                        |
                        v
                  +-----------+
                  |  FastAPI  |
                  +-----+-----+
                        |
                        v
                 Python Services
                        |
                +-------+-------+
                |               |
                v               v
      Application Logic     SQLAlchemy
                                |
                                v
                      Relational Database
```

FastAPI will act as the external API layer.

Python services will contain the actual application logic.

SQLAlchemy may be used to provide a clean Python-side access layer for structured relational data.

Future systems such as:

```text
Specific relational database
Vector retrieval
Agent orchestration
Caching
Model providers
Background workers
```

will be defined in separate ADRs.

---

## 7. Component Responsibilities

| Technology     | Primary Responsibility                             |
| -------------- | -------------------------------------------------- |
| **Python**     | Backend application and AI-oriented logic          |
| **FastAPI**    | HTTP API layer and routing                         |
| **Pydantic**   | Request, response, and structured data validation  |
| **SQLAlchemy** | Python-side access to structured relational data   |
| **Next.js**    | External frontend client consuming the backend API |

The responsibilities should remain clearly separated.

FastAPI should not become the location where all application logic is implemented.

Similarly, SQLAlchemy should be used as the database access layer rather than allowing database queries to be scattered throughout unrelated backend code.

---

## 8. Request Flow

A typical CareerGPS request may follow:

```text
Student
   ↓

Next.js Frontend
   ↓

POST /career/analyze
   ↓

FastAPI
   ↓

Validate request using Pydantic
   ↓

CareerGPS application logic
   ↓

Optional structured data access
through SQLAlchemy
   ↓

Produce structured response
   ↓

FastAPI
   ↓

JSON Response
   ↓

Next.js
   ↓

Updated UI
```

For example, the frontend may send:

```json
{
  "student_id": 123,
  "target_role": "AI Engineer"
}
```

The backend may eventually respond with:

```json
{
  "target_role": "AI Engineer",
  "strengths": ["Python", "REST APIs"],
  "gaps": ["Docker", "CI/CD"]
}
```

The frontend can then render this information without needing to understand how the backend produced it.

---

## 9. Positive Consequences

The selected backend stack provides:

- Strong compatibility with AI-oriented development
- Large Python AI and data-processing ecosystem
- Clear API-first architecture
- Structured request and response validation
- Automatic API documentation
- Good compatibility with the TypeScript frontend
- Strong async support
- Relatively low framework complexity
- High developer productivity
- Readable backend code
- Flexibility for future agent architecture
- Flexibility for future database and retrieval decisions
- Clean Python-side relational database access through SQLAlchemy
- Ability to use both ORM-style queries and raw SQL when appropriate
- Ability to keep deterministic computation and AI reasoning within the same backend environment

---

## 10. Negative Consequences and Trade-offs

### Multiple Programming Languages

The application will use:

```text
Frontend: TypeScript
Backend: Python
```

Developers working across the full stack may need to understand both languages.

This adds some context-switching compared with using TypeScript everywhere.

### Frontend and Backend Types Are Separate

Python models and TypeScript interfaces exist in different languages.

Without proper API contract management, they could become inconsistent.

FastAPI's OpenAPI schema should be used to reduce this risk.

### Python Is Not the Highest-Performance Backend Language

Languages such as Go or Java may provide stronger raw runtime performance for some workloads.

However, the primary bottlenecks in CareerGPS are expected to involve external AI services, network calls, retrieval, and analysis rather than CPU-bound HTTP request handling.

### FastAPI Should Not Become the Business Logic Layer

There is a risk that developers may place too much application logic directly inside FastAPI endpoints.

The team should maintain a separation between:

```text
API Layer
and
Application Logic
```

### SQLAlchemy Adds an Abstraction Layer

SQLAlchemy simplifies relational database access but also introduces ORM concepts that developers must understand.

For highly complex or performance-sensitive operations, raw SQL may still be more appropriate.

The team should therefore use SQLAlchemy as the default access layer without treating it as a rule that raw SQL can never be used.

---

## 11. Implementation Guidelines

The backend should follow these architectural guidelines:

1. Use **Python 3.12+** for backend development.

2. Use **FastAPI** for HTTP API endpoints.

3. Use **Pydantic** for request and response schemas.

4. Use **SQLAlchemy** as the preferred Python-side relational database access layer when structured database access is required.

5. Keep FastAPI endpoints small and focused.

For example:

```python
@app.post("/career/analyze")
async def analyze(request: CareerAnalysisRequest):
    return career_service.analyze(request)
```

rather than placing large amounts of application logic inside the endpoint itself.

6. Keep AI-specific logic outside the API route definitions.

7. Use structured request and response models instead of loosely defined dictionaries wherever practical.

8. Maintain a clear API contract with the Next.js frontend.

9. Use FastAPI's generated OpenAPI schema as the authoritative description of the backend API.

10. Keep SQLAlchemy models and database access logic separated from unrelated application logic.

11. Use raw SQL where justified by complexity or performance rather than forcing every database operation through ORM abstractions.

12. Do not expose model-provider credentials or internal secrets through API responses.

13. Keep future database, retrieval, orchestration, caching, and model-provider implementations behind the backend application layer.

---

## 12. Security Considerations

The backend should treat FastAPI as an external trust boundary.

Incoming data must be validated before being processed.

The backend should eventually enforce:

- Authentication
- Authorization
- Input validation
- Resource access controls
- Safe file handling
- Rate limiting where appropriate
- Protection of API keys and secrets

Authorization must be enforced by the backend rather than relying on the frontend to hide restricted functionality.

Detailed security architecture should be documented separately once authentication and authorization decisions are made.

---

## 13. Future Considerations

The following technologies and architectural decisions are intentionally outside the scope of this ADR:

- Specific relational database engine
- Vector database or vector extension
- Agent orchestration framework
- LLM provider
- Embedding model
- Reranking model
- Redis or another caching technology
- Background task framework
- Authentication provider
- Observability platform
- Evaluation framework

These decisions should be documented separately because they solve different architectural problems.

This allows the team to commit to:

```text
Python
+
FastAPI
+
Pydantic
+
SQLAlchemy as the preferred relational database access layer
```

without prematurely committing to the infrastructure that will operate behind them.

---

## 14. Final Decision Summary

CareerGPS will use **Python 3.12+** as its primary backend programming language and **FastAPI** as its backend API framework.

**Pydantic** will be used for structured request and response validation, while **SQLAlchemy** will be the preferred Python-side toolkit for interacting with structured relational data when database access is required.

Python was selected because CareerGPS is expected to involve significant AI, document-processing, data-analysis, retrieval, and evaluation workloads. Python provides a mature ecosystem for these requirements while allowing the team to combine deterministic application logic with AI-based processing.

FastAPI was selected because CareerGPS uses a separate Next.js frontend and therefore benefits from an API-focused backend rather than a server-rendered web framework. FastAPI provides clean endpoint development, structured validation through Pydantic, automatic OpenAPI documentation, async support, and strong compatibility with Python's AI ecosystem.

SQLAlchemy complements this architecture by providing a clean Python interface for future structured relational database access without locking the project into a specific database engine.

The high-level backend architecture will therefore be:

```text
Next.js Frontend
       ↓
     FastAPI
       ↓
      Python
       ↓
CareerGPS Application Logic
       ↓
   SQLAlchemy
       ↓
Future Relational Database
```

The exact database technology, agent orchestration framework, caching system, model provider, vector storage approach, and other infrastructure decisions will be evaluated and documented separately.

This keeps the backend architecture modular while giving CareerGPS a strong foundation for future AI, data, and agent-based functionality.
