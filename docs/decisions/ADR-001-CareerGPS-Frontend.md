# ADR-001: Frontend Technology Stack for CareerGPS

- **Status:** Pending Approval
- **Date:** 2026-10-07
- **Decision Owners:** CareerGPS Development Team
- **Project:** CareerGPS
- **Scope:** Frontend Architecture

---

## 1. Context

CareerGPS is an agentic career intelligence platform designed to help students understand how competitive they are for a target career and what actions they should take to improve their profile.

The frontend must support more than a chatbot-style interaction. It needs to present structured and interactive information such as:

- Student profile and résumé information
- Target career selection
- Market skill requirements
- Skill-gap analysis
- Opportunity recommendations
- Personalized project and learning roadmaps
- Supporting evidence and citations
- Agent progress and system explanations

CareerGPS compares a student's existing experience with labor-market requirements, identifies gaps, and converts those findings into concrete recommendations.

The system may also show structured outputs such as market-frequency statistics, strengths, weakly demonstrated skills, missing skills, and action recommendations.

The Microsoft project specification also requires a user-facing application or API capable of demonstrating multi-step task handling, source tracing, agent handoffs, and explainability.

Therefore, the frontend architecture must support a dynamic, component-based, maintainable web application that can interact efficiently with the CareerGPS backend.

---

## 2. Decision Drivers

The primary factors influencing the frontend technology decision are:

- Strong support for dynamic and interactive user interfaces
- Maintainability as the application grows
- Type safety for complex frontend/backend data
- Reusable UI components
- Clear application and routing structure
- Easy integration with the FastAPI backend
- Support for loading, error, and asynchronous states
- Strong developer ecosystem
- Ability for multiple developers to work on the frontend simultaneously
- Support for responsive and modern UI design
- Compatibility with visualization and dashboard libraries
- Low unnecessary architectural complexity

---

## 3. Decision

The CareerGPS frontend will use the following technology stack:

| Technology       | Role                                  |
| ---------------- | ------------------------------------- |
| **TypeScript**   | Primary frontend programming language |
| **React**        | Component-based UI library            |
| **Next.js**      | Frontend application framework        |
| **Tailwind CSS** | Styling framework                     |
| **shadcn/ui**    | Reusable UI component system          |

The frontend will communicate with the CareerGPS backend through HTTP APIs and, where appropriate, streaming connections.

The primary backend logic, agent orchestration, retrieval, database access, model routing, and AI processing will remain outside the frontend.

The high-level architecture is:

```text
User
  |
  v
Next.js Application
  |
  +-- React Components
  |
  +-- TypeScript
  |
  +-- Tailwind CSS
  |
  +-- shadcn/ui
  |
  v
FastAPI Backend
```

---

## 4. Technology Decisions and Rationale

### 4.1 TypeScript

#### Purpose

TypeScript will be used as the primary programming language for frontend development.

TypeScript extends JavaScript by adding static type checking.

For example, CareerGPS may receive a skill-gap object such as:

```typescript
interface SkillGap {
  skill: string;
  studentLevel: "none" | "some" | "strong";
  marketFrequency: number;
  priority: "low" | "medium" | "high";
}
```

#### Why We Selected It

CareerGPS will exchange large amounts of structured information between the frontend and backend.

Examples include:

```text
StudentProfile
MarketProfile
SkillGap
JobMatch
Recommendation
Roadmap
RoadmapTask
Citation
AgentExecution
AgentResult
```

TypeScript allows the frontend to explicitly define the expected structure of these objects.

This reduces runtime errors and makes incorrect data usage easier to identify during development.

#### Project-Specific Benefits

TypeScript is particularly useful for CareerGPS because the application will depend heavily on structured AI outputs.

For example, the Gap Analysis Agent is expected to identify:

- Existing strengths
- Missing skills
- Weakly demonstrated skills
- High-value gaps
- Lower-priority gaps

Instead of handling these values as loosely structured JavaScript objects, TypeScript allows the frontend to represent them through clearly defined interfaces.

This also improves collaboration because developers can understand the structure of the data without needing to inspect every API response manually.

---

### 4.2 React

#### Purpose

React will be used to construct the individual user-interface components of CareerGPS.

React allows the application to be divided into reusable components.

For example:

```text
Dashboard
│
├── ResumeUpload
├── StudentProfile
├── TargetRoleSelector
├── MarketAnalysis
├── SkillGapAnalysis
├── OpportunityCard
├── RecommendationCard
├── Roadmap
└── CitationPanel
```

#### Why We Selected It

CareerGPS requires a highly dynamic user interface.

A user may:

1. Upload a résumé.
2. Select a target career.
3. Trigger a market analysis.
4. Receive skill-gap results.
5. Change the target career.
6. Receive an updated analysis.

Only part of the interface should update when these changes occur.

React is designed around this type of state-driven interface.

#### Project-Specific Benefits

CareerGPS naturally maps backend outputs into frontend components.

For example:

```text
Student Profile Agent
        ↓
<StudentProfile />
```

```text
Market Intelligence Agent
        ↓
<MarketAnalysis />
```

```text
Gap Analysis Agent
        ↓
<SkillGapAnalysis />
```

```text
Opportunity Agent
        ↓
<OpportunityList />
```

```text
Action Agent
        ↓
<ActionPlan />
<Roadmap />
```

The proposed CareerGPS architecture includes distinct Profile, Market, Gap, Opportunity, and Action agents.

React's component model therefore aligns naturally with the system's multi-agent structure.

---

### 4.3 Next.js

#### Purpose

Next.js will provide the overall frontend application structure around React.

React will build the components, while Next.js will manage how those components are organized into a complete web application.

#### Why We Selected It

CareerGPS is expected to become a multi-page application rather than a single dashboard.

Possible application routes include:

```text
/dashboard
/profile
/market
/gaps
/opportunities
/roadmap
/settings
```

Next.js provides built-in conventions for:

- Routing
- Shared layouts
- Loading states
- Error handling
- Server/client component organization
- Production builds
- Application structure

For example:

```text
app/
│
├── dashboard/
│   └── page.tsx
│
├── profile/
│   └── page.tsx
│
├── market/
│   └── page.tsx
│
├── gaps/
│   └── page.tsx
│
└── roadmap/
    └── page.tsx
```

This gives the development team a predictable project structure.

#### Project-Specific Benefits

CareerGPS may need to show asynchronous agent progress while backend work is occurring.

For example:

```text
Analyzing Career Profile

Profile Agent      ✓ Complete
Market Agent       ✓ Complete
Gap Agent          ● Running
Action Agent       ○ Waiting
```

Next.js works well with React to manage loading states and dynamic interfaces while backend analysis is being performed.

It also allows the team to define shared application layouts.

For example:

```text
CareerGPS

Dashboard
Profile
Market
Skill Gaps
Opportunities
Roadmap
Settings
```

The navigation can remain consistent while the main content changes depending on the selected route.

---

### 4.4 Tailwind CSS

#### Purpose

Tailwind CSS will be used for frontend styling and responsive layout development.

#### Why We Selected It

CareerGPS will contain many repeated UI patterns including:

- Cards
- Tables
- Skill badges
- Progress indicators
- Navigation
- Forms
- Responsive grids
- Dashboard layouts

Tailwind allows developers to style these components quickly without maintaining a large collection of custom CSS files.

Example:

```tsx
<div className="rounded-lg border p-4">
  <h3 className="font-semibold">Docker</h3>
  <p>High-priority skill gap</p>
</div>
```

#### Project-Specific Benefits

Because multiple developers may work on separate frontend features, Tailwind provides a relatively consistent styling approach.

It also allows the team to focus development effort on CareerGPS-specific functionality rather than building and organizing a large custom CSS architecture.

---

### 4.5 shadcn/ui

#### Purpose

shadcn/ui will provide reusable frontend UI primitives.

Examples include:

- Buttons
- Cards
- Dialogs
- Tabs
- Tables
- Dropdowns
- Progress bars
- Forms
- Tooltips

#### Why We Selected It

CareerGPS requires a polished interface but does not need to develop every standard UI component from scratch.

Using reusable components reduces development time while still allowing substantial customization.

For example:

```text
<Card>
    Skill Gap Analysis
</Card>

<Progress />

<Tabs>
    Strong Match
    Potential Match
    Development Opportunity
</Tabs>
```

These components map naturally to CareerGPS functionality.

#### Project-Specific Benefits

The Opportunity Agent categorizes opportunities as:

- Strong Match
- Potential Match
- Development Opportunity

Reusable tab, card, badge, and progress components can represent these categories clearly while maintaining a consistent design language.

---

## 5. Alternatives Considered

### 5.1 JavaScript Instead of TypeScript

#### Why It Was Considered

JavaScript is simpler initially and is directly supported by browsers.

#### Advantages

- Lower initial learning curve
- Slightly less syntax
- Large ecosystem

#### Disadvantages for CareerGPS

JavaScript does not provide static type checking.

This increases the likelihood of errors involving complex objects such as:

```text
StudentProfile
MarketProfile
SkillGap
AgentResult
Citation
Roadmap
```

These types of objects will be exchanged frequently between the frontend and backend.

#### Why It Was Not Selected

CareerGPS is large enough that type safety provides more value than the small amount of additional TypeScript syntax.

**Decision:** TypeScript selected.

---

### 5.2 React + Vite Instead of Next.js

#### Why It Was Considered

React with Vite provides a lightweight and fast frontend development environment.

It would be sufficient for a simple single-page application.

#### Advantages

- Simple architecture
- Fast development server
- Less framework complexity
- Excellent for small React applications

#### Disadvantages for CareerGPS

Additional libraries and architectural decisions would be required for areas such as:

- Routing
- Layout structure
- Page organization
- Application conventions
- Some loading and error patterns

CareerGPS is expected to contain several product-style pages rather than a single isolated dashboard.

#### Why It Was Not Selected

Next.js gives the team stronger application-level conventions while still using React.

Because CareerGPS is expected to grow into a multi-page application, this structure is valuable.

**Decision:** Next.js selected over React + Vite.

---

### 5.3 Vue + Nuxt

#### Why It Was Considered

Vue and Nuxt provide a similar architecture to React and Next.js.

Vue is known for approachable syntax and a strong component model.

#### Advantages

- Good developer experience
- Component-based
- Strong documentation
- Nuxt provides routing and application structure

#### Disadvantages for CareerGPS

React has a broader ecosystem for many of the libraries and examples commonly associated with modern AI applications, dashboard interfaces, streaming responses, and application components.

Using React also provides a larger ecosystem of reusable libraries that may be useful as CareerGPS expands.

#### Why It Was Not Selected

Vue/Nuxt could successfully implement CareerGPS, but React/Next.js provides lower expected integration friction for the project's requirements.

**Decision:** React + Next.js selected.

---

### 5.4 Angular

#### Why It Was Considered

Angular provides a complete frontend framework with built-in support for routing, dependency injection, forms, and HTTP communication.

#### Advantages

- Highly structured
- Strong TypeScript integration
- Mature framework
- Suitable for large enterprise applications

#### Disadvantages for CareerGPS

Angular introduces more framework-specific concepts, including:

- Dependency injection
- Decorators
- Services
- RxJS
- Observables
- Angular-specific templates

This introduces unnecessary complexity for the project.

#### Why It Was Not Selected

The primary technical complexity of CareerGPS should remain focused on:

- Multi-agent systems
- Retrieval
- AI model routing
- Security
- Evaluation
- Agent orchestration

Adding additional frontend complexity provides little project-specific benefit.

**Decision:** React + Next.js selected.

---

### 5.5 Streamlit

#### Why It Was Considered

Streamlit allows AI and machine-learning applications to be prototyped extremely quickly using Python.

#### Advantages

- Very fast development
- Python only
- Easy integration with AI models
- Good for demos and prototypes

#### Disadvantages for CareerGPS

Streamlit provides less flexibility for building a polished, product-style web application.

CareerGPS requires features such as:

- Multi-page navigation
- Detailed dashboards
- Career profiles
- Skill visualizations
- Opportunity cards
- Roadmaps
- Agent explanations
- Responsive interfaces

#### Why It Was Not Selected

Streamlit would be appropriate for an early proof of concept but not for the planned CareerGPS frontend architecture.

**Decision:** Next.js + React selected.

---

## 6. Frontend Architecture Overview

The frontend architecture will be structured as follows:

```text
                     User Browser
                          |
                          v
                +-------------------+
                |      Next.js      |
                | Application Layer |
                +---------+---------+
                          |
          +---------------+----------------+
          |                                |
          v                                v
  React Components                  Application Routes
          |
          v
   TypeScript Types
          |
          v
   Tailwind CSS
   + shadcn/ui
          |
          v
    API Service Layer
          |
          v
      FastAPI Backend
```

The frontend will not directly access:

```text
LLM providers
PostgreSQL
Vector database
LangGraph agents
Embedding services
```

These interactions will occur through the backend.

---

## 7. Component Responsibilities

| Technology   | Primary Responsibility                                           |
| ------------ | ---------------------------------------------------------------- |
| TypeScript   | Type-safe frontend development                                   |
| React        | Reusable and dynamic interface components                        |
| Next.js      | Routing, layouts, page structure, frontend application framework |
| Tailwind CSS | Styling and responsive design                                    |
| shadcn/ui    | Reusable user-interface components                               |
| FastAPI      | External backend API consumed by frontend                        |

---

## 8. Data Flow

A typical frontend interaction may follow:

```text
User selects:
"AI Engineer"

       ↓

React updates target role

       ↓

Next.js frontend sends API request

       ↓

FastAPI backend

       ↓

CareerGPS agents perform analysis

       ↓

Backend returns structured response

       ↓

TypeScript-defined response objects

       ↓

React updates relevant components

       ↓

User sees:

Market Requirements
Skill Gaps
Recommendations
Supporting Evidence
```

For example:

```json
{
  "skill": "Docker",
  "studentLevel": "none",
  "marketFrequency": 0.39,
  "priority": "high"
}
```

could be rendered as:

```text
Docker

HIGH PRIORITY GAP

Appears in 39% of relevant jobs.

Current evidence:
No demonstrated Docker experience.
```

---

## 9. Positive Consequences

The selected frontend architecture provides:

- Strong type safety
- Reusable UI components
- Clear routing and page organization
- Consistent frontend architecture
- Faster frontend development
- Better maintainability
- Good integration with FastAPI
- Strong ecosystem support
- Good support for asynchronous agent workflows
- Easy implementation of loading and progress indicators
- Ability to build a polished product-style interface

---

## 10. Negative Consequences and Trade-offs

The decision introduces several trade-offs.

### Two Primary Programming Languages

The project will use:

```text
Frontend: TypeScript
Backend: Python
```

Developers working across the full stack must understand both.

### Next.js Adds Framework Complexity

Next.js introduces concepts beyond basic React, including:

- Server components
- Client components
- Route structure
- Layouts
- Rendering strategies

The team should avoid using unnecessary Next.js functionality.

### Potential Duplication of Types

Backend schemas may exist in Python while similar interfaces exist in TypeScript.

This creates the possibility that frontend and backend data definitions become inconsistent.

This should be mitigated through shared API specifications or generated types.

---

## 11. Implementation Guidelines

The frontend team should follow these architectural rules:

1. All frontend code should use **TypeScript**.

2. React components should be reusable where appropriate.

3. Next.js should primarily manage:

```text
Routing
Layouts
Page organization
Loading states
Error states
Frontend application behavior
```

4. Business and AI logic should remain in the FastAPI backend.

5. Frontend components must not directly call:

```text
OpenAI
Azure OpenAI
LangGraph
PostgreSQL
pgvector
Embedding APIs
```

6. Backend communication should go through a shared API service layer rather than scattered `fetch()` calls throughout UI components.

Recommended:

```text
lib/
└── api/
    ├── profile.ts
    ├── market.ts
    ├── gaps.ts
    ├── opportunities.ts
    └── roadmap.ts
```

7. Shared frontend types should be centrally defined.

Example:

```text
types/

├── profile.ts
├── market.ts
├── gaps.ts
├── opportunity.ts
├── roadmap.ts
└── agents.ts
```

8. Standard UI components should come from the project's shared component library rather than being recreated repeatedly.

9. Sensitive information and API credentials must never be stored directly in frontend source code.

---

## 12. Security Considerations

The frontend should follow the following security rules:

- API keys must never be exposed in browser code.
- Authentication and authorization must ultimately be enforced by the backend.
- The frontend should not be trusted to enforce access control.
- Sensitive résumé information should not be unnecessarily stored in browser local storage.
- File uploads must be validated by the backend.
- User-generated content should be rendered safely.
- Backend responses should be treated as structured application data rather than executable content.

These concerns align with the broader project requirement for authentication, role-based access control, authorization boundaries, audit logging, and defenses against data leakage.

---

## 13. Future Considerations

The following decisions are intentionally not finalized in this ADR:

- Authentication provider
- Charting and visualization library
- Advanced client-side state-management library
- Frontend observability platform
- WebSocket versus Server-Sent Events for agent progress
- Progressive Web App support
- Mobile application support
- Accessibility tooling beyond baseline frontend practices

These should only be introduced when concrete requirements justify them.

---

## 14. Final Decision Summary

CareerGPS will use **TypeScript, React, and Next.js** as its primary frontend technology stack, with **Tailwind CSS** for styling and **shadcn/ui** for reusable interface components.

TypeScript was selected because CareerGPS relies heavily on structured data flowing between the frontend and backend.

React was selected because CareerGPS requires reusable and dynamically updating interface components.

Next.js was selected because the application is expected to grow into a structured, multi-page product requiring routing, shared layouts, loading states, error handling, and consistent architectural conventions.

Tailwind CSS and shadcn/ui were selected to accelerate interface development while maintaining design consistency.

The frontend will remain focused on user interaction and presentation, while the primary business logic, AI orchestration, retrieval, database access, and model interaction will remain within the FastAPI backend.

The resulting frontend stack is therefore:

```text
TypeScript
    ↓
React
    ↓
Next.js
    ↓
Tailwind CSS + shadcn/ui
    ↓
FastAPI Backend
```

This architecture provides an appropriate balance between development speed, maintainability, team collaboration, and the interactive user experience required by CareerGPS.
