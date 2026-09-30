const DATA = {
  student: { name: "Alex Johnson", first: "Alex", email: "alex.johnson@wisc.edu", university: "University of Wisconsin–Madison", gradYear: "2027", role: "AI Engineer", level: "Full-time", location: "United States" },

  readiness: { overall: 72, cats: [
    ["Technical Skills", 78], ["Projects", 74], ["Experience", 82], ["Cloud / DevOps", 46], ["AI / ML", 76]
  ]},

  skills: {
    strong: [
      ["Python", "Developed Python-based ML pipelines during IndustrialMind AI internship.", ["Job 12", "Resume"]],
      ["React", "Built a responsive dashboard in React for a course capstone project.", ["Resume"]],
      ["REST APIs", "Designed and documented REST endpoints for an internal analytics service.", ["Resume"]],
      ["LLM APIs", "Integrated OpenAI and Anthropic APIs into a summarization tool (GitHub repo: notes-ai).", ["Resume", "Job 24"]],
      ["PyTorch", "Trained and evaluated a text classifier in PyTorch for CS 540.", ["Resume"]],
      ["Software Engineering Internship", "Software engineering intern at IndustrialMind AI, summer 2026.", ["Resume"]]
    ],
    some: [
      ["SQL", "Wrote queries for reporting during coursework; no production database ownership shown.", ["Resume"]],
      ["AWS", "Used S3 and EC2 in one class project; no deployment pipeline shown.", ["Resume", "Job 31"]],
      ["Cloud Deployment", "One project deployed manually to a single VM.", ["Resume"]],
      ["Machine Learning", "Coursework and one internship project; limited end-to-end ownership.", ["Resume", "O*NET"]]
    ],
    none: [
      ["Docker", "No containerization evidence found in résumé, projects, or coursework.", ["Job 12", "Job 24"]],
      ["CI/CD", "No automated testing or deployment workflow found.", ["Job 24", "Job 40"]],
      ["Vector Databases", "No retrieval or embedding-store usage found.", ["Job 18", "Job 24"]],
      ["Kubernetes", "No orchestration evidence found.", ["Job 31"]]
    ]
  },

  market: [
    ["Python", 84], ["SQL", 56], ["Cloud Platforms", 51], ["Docker", 39], ["LLM / RAG", 34], ["CI/CD", 30], ["Kubernetes", 22]
  ],
  responsibilities: [
    "Build and deploy machine learning systems", "Develop AI-powered applications", "Build data and inference pipelines",
    "Integrate LLM APIs", "Deploy services to cloud infrastructure", "Monitor and evaluate production models"
  ],

  gaps: [
    { skill: "Docker", pri: "High", demand: 39, evidence: "No demonstrated experience",
      why: "Docker appears frequently across retrieved AI Engineer opportunities, but your résumé currently contains no demonstrated containerization experience.",
      action: "Add Docker to your next deployed AI project.", cites: ["Job 12", "Job 24", "O*NET"] },
    { skill: "CI/CD", pri: "High", demand: 30, evidence: "No demonstrated experience",
      why: "Automated testing and deployment show up in roughly a third of postings and signal production readiness.",
      action: "Set up GitHub Actions to automatically test and deploy one of your projects.", cites: ["Job 24", "Job 40"] },
    { skill: "Vector Databases", pri: "High", demand: 34, evidence: "No demonstrated experience",
      why: "Vector search underpins RAG, the most common LLM application pattern in the retrieved roles.",
      action: "Add a vector database to a retrieval project and evaluate retrieval quality.", cites: ["Job 18", "Job 24"] },
    { skill: "Kubernetes", pri: "Medium", demand: 22, evidence: "No demonstrated experience",
      why: "Kubernetes appears in some AI infrastructure roles but is less common than Docker and cloud deployment for entry-level positions.",
      action: "Learn the basics after Docker; deploy one service to a local cluster.", cites: ["Job 31"] },
    { skill: "AWS depth", pri: "Lower", demand: 51, evidence: "Some experience",
      why: "You already have partial exposure. Deepening it is valuable but less urgent than the gaps above.",
      action: "Deploy your RAG project on AWS as part of the roadmap.", cites: ["Job 31", "O*NET"] }
  ],

  weeks: [
    ["Document Ingestion Pipeline", ["Upload and parse documents", "Chunk documents", "Store metadata", "Create embeddings"]],
    ["Retrieval System", ["Add vector database", "Implement semantic retrieval", "Evaluate retrieval quality"]],
    ["Docker", ["Create Dockerfile", "Containerize application", "Test local deployment"]],
    ["CI/CD", ["Add automated tests", "Configure GitHub Actions", "Build deployment workflow"]],
    ["Deployment + Evaluation", ["Deploy application", "Add evaluation metrics", "Write project documentation", "Update résumé"]]
  ],

  projects: [
    { name: "Production RAG Assistant", skills: ["RAG", "Vector Databases", "Docker", "CI/CD", "Cloud Deployment"], impact: "Addresses 3 high-priority gaps", weeks: 5, diff: "Intermediate", best: true },
    { name: "ML Model Deployment API", skills: ["Docker", "CI/CD", "REST APIs", "AWS"], impact: "Addresses 2 high-priority gaps", weeks: 3, diff: "Beginner", best: false },
    { name: "AI Recommendation System", skills: ["Vector Databases", "Python", "SQL", "Evaluation"], impact: "Addresses 1 high-priority gap", weeks: 4, diff: "Intermediate", best: false },
    { name: "Multimodal Search Application", skills: ["Embeddings", "Vector Databases", "Docker", "React"], impact: "Addresses 2 high-priority gaps", weeks: 6, diff: "Advanced", best: false }
  ],

  courses: [
    ["CS 544 — Big Data Systems", "Recommended because distributed systems and containerized data infrastructure frequently appear in AI engineering roles.", ["Docker", "Cloud"]],
    ["CS 639 — Cloud Computing", "Recommended because cloud deployment appears in 51% of analyzed postings and your AWS evidence is partial.", ["AWS", "Cloud Deployment"]],
    ["CS 540 — Introduction to Artificial Intelligence", "Recommended to strengthen AI / ML fundamentals, your second-strongest readiness category.", ["Machine Learning", "PyTorch"]]
  ],
  clubs: [
    { name: "AI Club", skills: ["LLM apps", "RAG", "Model evaluation"], event: "Build Night: RAG in a weekend · Oct 9", why: "Members ship LLM projects together, which matches your highest-impact next step." },
    { name: "Data Science Club", skills: ["SQL", "Vector search", "Data pipelines"], event: "Workshop: Embeddings 101 · Oct 14", why: "Helps you turn coursework SQL and ML into demonstrated project evidence." },
    { name: "ACM", skills: ["CI/CD", "Docker", "Git workflows"], event: "DevOps for Students · Oct 21", why: "Hands-on sessions cover the exact infrastructure skills missing from your profile." },
    { name: "Robotics Club", skills: ["Systems", "Deployment", "Teamwork"], event: "Open Build Day · Oct 28", why: "Lower priority; builds deployment and systems experience on real hardware." }
  ],
  hacks: [
    { name: "Hackathons", title: "BadgerHacks Fall", date: "Nov 8–9", skills: ["Docker", "Rapid prototyping"], team: "2–4", status: "Open" },
    { name: "Project Marathons", title: "AI 30-Day Build Sprint", date: "Oct 15 – Nov 15", skills: ["RAG", "CI/CD"], team: "1–3", status: "Open" },
    { name: "Case Competitions", title: "Applied ML Case Challenge", date: "Nov 22", skills: ["Model evaluation", "Communication"], team: "3–4", status: "Opens Oct 20" },
    { name: "AI Challenges", title: "Kaggle Playground Series", date: "Rolling", skills: ["Python", "ML pipelines"], team: "1", status: "Open" }
  ],
  learning: [
    ["Microsoft Learn", "Containerize apps with Docker", "Docker"],
    ["Coursera", "Vector Databases and Semantic Search", "Vector Databases"],
    ["Kaggle Learn", "Intro to ML Model Deployment", "Machine Learning"],
    ["GitHub Skills", "Hello GitHub Actions", "CI/CD"]
  ],

  sources: {
    "Job 12": { title: "AI Engineer, New Grad", org: "Public job posting dataset", text: "Requires Python; Docker for packaging inference services; familiarity with cloud deployment." },
    "Job 18": { title: "Machine Learning Engineer, Entry Level", org: "Public job posting dataset", text: "Build retrieval pipelines using vector databases; experience with embeddings preferred." },
    "Job 24": { title: "AI Application Engineer", org: "Public job posting dataset", text: "Ship LLM-powered features; Docker, CI/CD and vector database experience a plus." },
    "Job 31": { title: "ML Platform Engineer, New Grad", org: "Public job posting dataset", text: "AWS, Kubernetes for model serving; monitor production models." },
    "Job 40": { title: "Software Engineer, AI", org: "Public job posting dataset", text: "Own CI/CD for ML services with automated tests and staged deploys." },
    "O*NET": { title: "O*NET occupational data", org: "U.S. Dept. of Labor", text: "Occupational profile for AI / ML engineers: programming, data pipelines, systems deployment, model monitoring." },
    "Resume": { title: "Your résumé", org: "Uploaded by you", text: "Evidence extracted from your résumé, coursework and linked projects." }
  },

  copilot: {
    "What should I focus on this semester?": { a: "Focus on one deployable project: a production-ready RAG application. It closes Docker, CI/CD and vector database gaps in one build, over about five weeks. Pair it with CS 639 to strengthen cloud depth.", c: ["Job 24", "O*NET"] },
    "Why is Docker a high-priority gap?": { a: "Based on the 64 AI Engineer roles currently in your market dataset, Docker appears in 39% of relevant opportunities. Your résumé currently shows no containerization experience, so adding Docker to your next project would strengthen an important missing area.", c: ["Job 12", "Job 24", "O*NET"] },
    "What jobs am I currently competitive for?": { a: "You are strongest for AI Engineer and Software Engineer (AI) new-grad roles that emphasize Python, REST APIs and LLM integration. Roles that require Docker, CI/CD or Kubernetes are stretch targets until you close those gaps.", c: ["Job 12", "Job 40"] },
    "What project would improve my profile the most?": { a: "A Production RAG Assistant. It demonstrates RAG, vector databases, Docker, CI/CD and cloud deployment, addressing 3 high-priority gaps.", c: ["Job 18", "Job 24"] },
    "Which UW–Madison courses could help me?": { a: "CS 544 (Big Data Systems), CS 639 (Cloud Computing) and CS 540 (Introduction to Artificial Intelligence) map most directly to your gaps in cloud infrastructure and AI fundamentals.", c: ["O*NET", "Job 31"] }
  }
};
