"""
Claude API-based circuit optimization agent.
Reads schematic netlist + sim results, returns parameter suggestions.
"""

import json
from typing import Any, Dict, List

ANTHROPIC_AVAILABLE = False
try:
    import anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    pass


SYSTEM_PROMPT = """You are an expert analog/mixed-signal IC design engineer.
You help optimize circuit parameters to meet user-specified design goals.

Given:
- The circuit netlist (SPICE format)
- Current component parameters (W, L, R, C values, etc.)
- Simulation results (if available)
- User's design goals and target specifications

Your task is to suggest specific parameter changes to help meet the design goals.

Rules:
1. Only suggest changes to EXISTING component parameters (don't add or remove components)
2. Be specific: give exact values (e.g., "Change M1 W from 2u to 6u")
3. Explain WHY each change helps
4. Respect device limits (e.g., L >= Lmin for the process)
5. For IHP SG13G2: LV NMOS/PMOS Lmin=0.13u, HV Lmin=0.45u, max W per finger=10u
6. Suggest 1-5 changes per iteration, ordered by expected impact
7. After each suggestion set, summarize expected effect on the target specs

Output format (always use this JSON structure):
{
  "suggestions": [
    {
      "component": "M1",
      "parameter": "w",
      "old_value": "2u",
      "new_value": "6u",
      "reason": "Increase drive strength to boost gain"
    }
  ],
  "summary": "These changes should increase gain by ~6dB by raising gm of M1.",
  "next_step": "Re-simulate and check gain at 1MHz"
}
"""


class OptimizationAgent:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.history: List[Dict] = []
        self._client = None

    def set_api_key(self, key: str):
        self.api_key = key
        self._client = None

    def _get_client(self):
        if not ANTHROPIC_AVAILABLE:
            raise RuntimeError("anthropic package not installed. Run: pip install anthropic")
        if not self.api_key:
            raise RuntimeError("Anthropic API key not set.")
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def reset_history(self):
        self.history = []

    def get_suggestions(
        self,
        netlist: str,
        design_goals: str,
        current_params: Dict[str, Any],
        sim_results: str = "",
        iteration: int = 0,
    ) -> Dict:
        """
        Ask Claude for parameter optimization suggestions.
        Returns dict with 'suggestions', 'summary', 'next_step' or 'error'.
        """
        try:
            client = self._get_client()
        except Exception as e:
            return {"error": str(e), "suggestions": [], "summary": "", "next_step": ""}

        user_content = f"""=== CIRCUIT NETLIST ===
{netlist}

=== CURRENT PARAMETERS ===
{json.dumps(current_params, indent=2)}

=== DESIGN GOALS ===
{design_goals}
"""
        if sim_results:
            user_content += f"\n=== SIMULATION RESULTS ===\n{sim_results}\n"

        if iteration > 0:
            user_content += f"\nThis is iteration {iteration + 1}. Previous suggestions were applied."

        self.history.append({"role": "user", "content": user_content})

        try:
            response = client.messages.create(
                model="claude-opus-4-8",
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=self.history,
            )
            reply = response.content[0].text
            self.history.append({"role": "assistant", "content": reply})

            import re

            json_match = re.search(r"\{[\s\S]*\}", reply)
            if json_match:
                return json.loads(json_match.group())
            return {"suggestions": [], "summary": reply, "next_step": ""}
        except Exception as e:
            return {"error": str(e), "suggestions": [], "summary": "", "next_step": ""}

    def explain_circuit(self, netlist: str, question: str) -> str:
        """Free-form question about the circuit."""
        client = self._get_client()
        try:
            response = client.messages.create(
                model="claude-opus-4-8",
                max_tokens=1024,
                system=(
                    "You are an expert analog IC design engineer. Answer questions about "
                    "circuit netlists clearly and concisely."
                ),
                messages=[
                    {
                        "role": "user",
                        "content": f"Netlist:\n{netlist}\n\nQuestion: {question}",
                    }
                ],
            )
            return response.content[0].text
        except Exception as e:
            return f"Error: {e}"
