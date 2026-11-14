import { resources } from "../../test/fixtures";
import type { Resource } from "../../types/api";

const SCHOOL = "University of Wisconsin–Madison";

const course = (id: string, title: string, skills: string[], guide: Partial<Resource> = {}): Resource => ({
  id, type: "school_course", title, provider: "UW–Madison course", meta: "Check the course guide for terms",
  description: "", skills, url: "https://guide.wisc.edu/courses/comp_sci/", school: SCHOOL, alongside: false, ...guide,
});

/** Three UW–Madison courses; the ids are the catalog's. COMP SCI 564 closes the SQL gap in the shared fixtures. */
export const uwCourses: Resource[] = [
  course("uw-cs-320", "COMP SCI 320: Data Science Programming II", ["analytical_scripting"],
    { meta: "4 credits · Last taught Fall 2026", description: "Intermediate approach to Data Science programming using Python.",
      course_code: "COMP SCI 320", credits: "4", last_taught: "Fall 2026" }),
  course("uw-cs-564", "COMP SCI 564: Database Management Systems: Design and Implementation", ["sql"],
    { meta: "4 credits · Last taught Fall 2026", description: "What a database management system is; different data models.",
      course_code: "COMP SCI 564", credits: "4", last_taught: "Fall 2026" }),
  course("uw-stat-240", "STAT 240: Data Science Modeling I", ["statistics", "analytical_scripting"],
    { url: "https://guide.wisc.edu/courses/stat/" }),
];

/** What GET /resources lists for a UW–Madison student: the shared resources plus the school's courses. */
export const uwResources: Resource[] = [...resources, ...uwCourses];
