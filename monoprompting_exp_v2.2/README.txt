✨ BridgeCode v2.2 (Experimental) Prompt Files Explained ✨

This system uses a streamlined, three-phase approach for code generation, enhanced with improved reasoning methods (Flow of Thought & the new Spark of Thought).

Here's what each file does:

Phase 1: Planning 📝
📄 slow_planning.yaml
   🔹 Purpose: Guides the AI through detailed, methodical planning BEFORE writing code.
   🔹 Uses:
      ▪️ MONOCODE Planning Principles: Focuses on designing for failure, understanding constraints, planning tests, and incremental delivery.
      ▪️ FLOW_OF_THOUGHT: Employs step-by-step, detailed reasoning (Decomposition, Structured Responses, Reflection, Solve, Refine, AoT) to create a robust text-based plan.
   🔹 Goal: Produce a well-thought-out architectural plan (text only).

Phase 2: Implementation 💡
📄 new_code.yaml
   🔹 Purpose: Guides the AI to write the actual code, experimenting with the *new, faster* Spark of Thought reasoning.
   🔹 Uses:
      ▪️ MONOCODE Implementation Principles: Focuses on making code observable, handling errors explicitly, managing dependencies transparently, and building progressively.
      ▪️ SPARK_OF_THOUGHT: Employs ultra-efficient, heuristic-driven reasoning (Direct Path, Heuristic Root Cause, Immediate Answer, Atomic Efficiency) for rapid code generation. (Note: Still experimental).
   🔹 Goal: Generate functional code efficiently based on a plan or request.

Phase 3: Debugging 🐞
📄 cause_debugging.yaml
   🔹 Purpose: Guides the AI through systematic debugging to find the root cause of errors in existing code.
   🔹 Uses:
      ▪️ MONOCODE Debugging Principles: Focuses on isolating issues, forming hypotheses, fixing methodically, and documenting the cause.
      ▪️ FLOW_OF_THOUGHT: Uses detailed, step-by-step reasoning to analyze symptoms, test hypotheses, and pinpoint the error source.
   🔹 Goal: Identify and explain the cause of a bug.

---

Secondary Modification Prompts ⚙️
These are used *in addition to* a phase prompt (usually Implementation or Debugging) to modify *how* the AI approaches changing code:

📄 code_expansion.yaml
   🔹 Purpose: Tells the AI to *preserve* existing working code.
   🔹 Approach: Make minimal changes; only modify parts explicitly identified as needing fixes or improvements. Avoid breaking stable functionality. Good for careful additions.

📄 code_contraction.yaml
   🔹 Purpose: Tells the AI to find *alternative solutions* or refactor.
   🔹 Approach: Break out of current patterns if they seem ineffective; try different algorithms or structures. Encourages creativity when stuck or code is clumsy.

📄 code_implosion.yaml
   🔹 Purpose: Tells the AI to *completely rewrite* the code.
   🔹 Approach: Delete the existing implementation and build from scratch based on first principles and requirements. Used for fundamentally flawed code.

---

Overall, this structure separates planning, coding, and debugging into distinct phases, while the secondary files offer specific strategies for how code should be modified within those phases.