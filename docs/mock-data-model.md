# Mock Banner Data Model

## Purpose

This document defines the initial synthetic academic data model for the UNA MCP AI Scheduling Research Project.

The mock data model is intended to support development and testing of the scheduling assistant without connecting to the real UNA Banner system.

The model should be detailed enough to support prerequisite checking, section lookup, schedule-conflict detection, credit-hour validation, and schedule generation while remaining small enough for an initial research prototype.

---

## Source-of-Truth Classification

### CONFIRMED

- Development will use a mock Banner HTTP API.
- No connection to the real UNA Banner system will be attempted during the current development phase.
- All student and academic records used during development will be synthetic.
- The MCP server should interact with the academic backend through a stable interface so the mock backend can later be replaced with a UNA-approved Banner integration.

### RECOMMENDATION

The initial mock academic system will contain the following entities:

1. Student
2. Course
3. CourseHistory
4. Term
5. Section
6. Enrollment

### WORKING ASSUMPTION

The first prototype will support simple prerequisite and corequisite rules in which all listed requirements must be satisfied.

More complex rules such as:

- Course A OR Course B
- minimum grades
- minimum GPA
- placement scores
- instructor approval
- program restrictions

may be added later if required.

### OPEN QUESTION

Future versions may require degree-program requirements, catalog-year information, or degree-audit data if the system is expected to answer questions such as:

"What courses do I still need to graduate?"

The first prototype will focus primarily on scheduling courses selected or requested by the student.

---

# 1. Student

## Purpose

Represents a synthetic student using the scheduling system.

Only information required for scheduling should be stored.

## Proposed Fields

- `student_id`
- `display_name`
- `program`
- `max_credit_hours`
- `active`

## Example

```json
{
  "student_id": "S10001",
  "display_name": "Alex Student",
  "program": "Information Technology",
  "max_credit_hours": 18,
  "active": true
}
```

## Security Considerations

The mock system should not include unnecessary personally identifiable information.

Examples of data that should not be included unless a future requirement specifically needs them:

- Social Security numbers
- home addresses
- phone numbers
- personal email addresses
- dates of birth
- financial information

The project should follow the principle of data minimization.

---

# 2. Course

## Purpose

Represents an academic course independent of a specific semester or section.

A Course describes what the class is.

A Section describes a specific offering of the class.

## Proposed Fields

- `course_id`
- `subject`
- `course_number`
- `title`
- `credit_hours`
- `prerequisites`
- `corequisites`

## Example

```json
{
  "course_id": "CIS376",
  "subject": "CIS",
  "course_number": "376",
  "title": "Example Networking Course",
  "credit_hours": 3,
  "prerequisites": [
    "CIS330"
  ],
  "corequisites": []
}
```

## Initial Rule

For the first prototype, every course listed in `prerequisites` must be successfully completed before the student is considered eligible.

For example:

```json
"prerequisites": [
  "CIS330",
  "CIS340"
]
```

initially means:

```text
CIS330 AND CIS340
```

More advanced prerequisite expressions may be designed later.

---

# 3. CourseHistory

## Purpose

Represents a student's previous course attempts and results.

Course history will be stored separately from the Student object so academic attempts can retain information such as term, grade, and completion status.

## Proposed Fields

- `student_id`
- `course_id`
- `term_id`
- `grade`
- `status`

## Example

```json
{
  "student_id": "S10001",
  "course_id": "CIS330",
  "term_id": "2026FA",
  "grade": "B",
  "status": "completed"
}
```

## Possible Status Values

Initial values may include:

- `completed`
- `in_progress`
- `failed`
- `withdrawn`

The exact values should be finalized before implementation.

---

# 4. Term

## Purpose

Represents an academic period.

Sections must reference a Term so courses offered in different semesters are not accidentally mixed together.

## Proposed Fields

- `term_id`
- `name`
- `start_date`
- `end_date`

## Example

```json
{
  "term_id": "2027SP",
  "name": "Spring 2027",
  "start_date": "2027-01-11",
  "end_date": "2027-05-07"
}
```

---

# 5. Section

## Purpose

Represents a specific offering of a Course during a Term.

A single Course may have multiple Sections.

Example:

```text
CIS 376
├── Section 01
├── Section 02
└── Section 03
```

Each Section may have different meeting times, capacities, or delivery methods.

## Proposed Fields

- `section_id`
- `course_id`
- `term_id`
- `section_number`
- `modality`
- `capacity`
- `enrolled_count`
- `meetings`

## Example

```json
{
  "section_id": "SEC1001",
  "course_id": "CIS376",
  "term_id": "2027SP",
  "section_number": "01",
  "modality": "in_person",
  "capacity": 30,
  "enrolled_count": 24,
  "meetings": [
    {
      "days": [
        "MON",
        "WED"
      ],
      "start_time": "09:30",
      "end_time": "10:45",
      "location": "Building A 101"
    }
  ]
}
```

## Meeting Structure

`meetings` should be an array rather than a single meeting.

This allows a Section to represent multiple required meeting components, such as:

```text
Lecture
+
Lab
```

without changing the Section schema.

Possible day values may include:

- `MON`
- `TUE`
- `WED`
- `THU`
- `FRI`
- `SAT`
- `SUN`

---

# 6. Enrollment

## Purpose

Represents the relationship between a student and a specific Section.

## Proposed Fields

- `student_id`
- `section_id`
- `status`

## Example

```json
{
  "student_id": "S10001",
  "section_id": "SEC1001",
  "status": "enrolled"
}
```

## Proposed Schedule Handling

The system does not need to create permanent Enrollment records merely to test possible schedules.

A proposed schedule may instead be represented temporarily as a list of Section IDs.

Example:

```json
[
  "SEC1001",
  "SEC2042",
  "SEC3107"
]
```

Deterministic scheduling logic can then validate that collection before presenting it to the student.

---

# Entity Relationships

The conceptual relationships are:

```text
STUDENT
   |
   |---- has --------> COURSE HISTORY
   |                        |
   |                        v
   |                      COURSE
   |
   |---- enrolled ----> SECTION
                            |
                            |---- belongs to ----> COURSE
                            |
                            |---- belongs to ----> TERM
```

Courses may also reference other Courses:

```text
COURSE
  |
  |---- prerequisites ----> COURSE
  |
  |---- corequisites -----> COURSE
```

---

# Deterministic Rules Supported by This Model

The initial data model should eventually allow deterministic application logic to answer questions such as:

- What courses has the student completed?
- Does the student satisfy the prerequisites for a course?
- Does the student satisfy required corequisites?
- What Sections are available for a Course during a Term?
- Does a Section have remaining capacity?
- Do two Sections overlap in time?
- How many credit hours are included in a proposed schedule?
- Does the proposed schedule exceed the student's credit-hour limit?
- Is a student already enrolled in a Section or Course?

The AI language model should not independently decide these academic rules.

The AI may request, interpret, and explain results, but deterministic application logic must perform academic validation.

---

# Initial MVP Scope

The first scheduling prototype should support a workflow similar to:

```text
Student selects or requests courses
        |
        v
Retrieve student academic history
        |
        v
Check prerequisites/corequisites
        |
        v
Find Sections for the selected Term
        |
        v
Check Section availability
        |
        v
Detect scheduling conflicts
        |
        v
Validate credit-hour limits
        |
        v
Generate valid schedule options
        |
        v
AI explains the validated options
```

The first prototype is not intended to reproduce a complete academic advising or degree-audit platform.

---

# Future Expansion

Possible future data requirements include:

- degree requirements
- catalog year
- concentrations
- general education requirements
- elective requirements
- minimum prerequisite grades
- GPA requirements
- instructor approval
- department restrictions
- waitlists
- section registration status
- online asynchronous Sections
- variable-credit Courses

These should only be introduced if the research scope requires them.

---

# Design Principle

The mock data model should remain:

- small
- understandable
- testable
- synthetic
- secure
- replaceable

The goal is not to reproduce Banner internally.

The goal is to create the minimum academic abstraction needed to research how an AI agent can safely use MCP tools to assist with class scheduling.
