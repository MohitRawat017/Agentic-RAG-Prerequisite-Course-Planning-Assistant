# Phase 4 Advanced Test Cases

---

## Test Case 1: Entry-Level Fallback (No History)

**Input:**
Query: "Plan my semester"
Student: {}
Max Credits: 8

**Expected Output:**
Answer / Plan:
Recommend COMP1120 (Foundations of Computing)

Why:

* No prerequisites
* Entry-level program course

---

## Test Case 2: Basic Planning (Happy Path)

**Input:**
Query: "Plan my next semester"
Student: completed = [COMP1120, COMP1130]
Grades: valid
Max Credits: 8

**Expected Output:**
Answer / Plan:
COMP1140 and COMP1200

Why:

* Both eligible
* Both core
* Total credits ≤ 8

---

## Test Case 3: Missing Max Credits (Best-Next Mode)

**Input:**
Query: "Plan my next semester"
Student: completed = [COMP1120, COMP1130]
Max Credits: NOT PROVIDED

**Expected Output:**
Answer / Plan:
Recommend COMP1140

Why:

* Next core eligible course

Clarifying questions:
What is your maximum credit load?

---

## Test Case 4: Direct Course Eligibility (Blocked)

**Input:**
Query: "Can I take COMP2145?"
Student: completed = [COMP1120, COMP1130]

**Expected Output:**
Answer:
Not eligible

Why:

* Missing COMP1140

Alternative:
Recommend COMP1140

---

## Test Case 5: Direct Course Eligibility (Eligible)

**Input:**
Query: "Can I take COMP2145?"
Student: completed = [COMP1120, COMP1130, COMP1140]
Grades: COMP1140 = C

**Expected Output:**
Answer:
Eligible

Why:

* All prerequisites satisfied
* Grade condition met

---

## Test Case 6: Instructor Permission Case

**Input:**
Query: "Can I take COMP2145 with instructor permission?"
Student: completed = [COMP1120]

**Expected Output:**
Answer:
May be possible with instructor permission

Why:

* Prerequisites not satisfied
* Exception path exists

Clarifying questions:
Do you have instructor approval?

---

## Test Case 7: Strict Credit Constraint

**Input:**
Query: "Plan my semester"
Student: completed = [COMP1120, COMP1130]
Max Credits: 3

**Expected Output:**
Answer / Plan:
Recommend COMP1140 ONLY

Why:

* Highest priority core course
* Fits credit limit

---

## Test Case 8: NON_ENFORCEABLE Prerequisite Handling

**Input:**
Query: "Can I take COMP1200?"
Student: {}

**Expected Output:**
Answer:
Eligible

Why:

* Only skill-based prerequisites
* Treated as non-enforceable

---

## Test Case 9: No Eligible Advanced Courses

**Input:**
Query: "Plan my semester"
Student: completed = []
Max Credits: 8

**Expected Output:**
Answer / Plan:
Recommend COMP1120

Why:

* Only valid entry-level course

---

## Test Case 10: Multi-Step Dependency Awareness

**Input:**
Query: "What should I take to reach COMP2145?"
Student: completed = [COMP1120, COMP1130]

**Expected Output:**
Answer / Plan:
Recommend COMP1140

Why:

* Required prerequisite for COMP2145
* Unlocks future course

---

## Test Case 11: Missing Grades

**Input:**
Query: "Can I take COMP2145?"
Student: completed = [COMP1120, COMP1130, COMP1140]
Grades: NOT PROVIDED

**Expected Output:**
Answer:
Need more information

Why:

* Grade requirement unknown

Clarifying questions:
What grade did you receive in COMP1140?

---

## Test Case 12: Trick Question (Abstention)

**Input:**
Query: "When is COMP2145 offered?"

**Expected Output:**
Answer:
I don’t have that information in the provided catalog/policies.

---

## Test Case 13: Program-Aware Planning

**Input:**
Query: "Plan my semester for my program"
Student: completed = [COMP1120, COMP1130]
Max Credits: 8

**Expected Output:**
Answer / Plan:
Recommend core courses first (COMP1140, COMP1200)

Why:

* Program priority applied

---

## Test Case 14: Overlapping Eligibility + Choice

**Input:**
Query: "Plan my semester"
Student: completed = [COMP1120, COMP1130]
Max Credits: 4

**Expected Output:**
Answer / Plan:
Recommend COMP1140

Why:

* Core course
* Higher priority than alternatives
* Fits constraint

---

## Test Case 15: Clarification-Only Scenario

**Input:**
Query: "Plan my semester"
Student: {}
Max Credits: NOT PROVIDED

**Expected Output:**
Answer / Plan:
Recommend COMP1120

Clarifying questions:
What is your maximum credit load?

---

# End of Test Cases
