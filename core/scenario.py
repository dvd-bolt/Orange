import os
import json
import logging
import ast
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger("scenario_engine")

class ScenarioValidationError(Exception):
    """Exception raised when a scenario fails validation."""
    pass

class ScenarioEngine:
    """
    ScenarioEngine processes declarative YAML/JSON steps, validates them,
    and executes them sequentially or conditionally.
    """
    def __init__(self, vault_path: Optional[str] = None):
        self.vault_path = vault_path
        self.context: Dict[str, Any] = {}
        self.history: List[Dict[str, Any]] = []

    def parse_scenario(self, content: str) -> Dict[str, Any]:
        """Parses a scenario from a YAML or JSON string."""
        content = content.strip()
        if not content:
            raise ScenarioValidationError("Scenario content is empty")
        
        # Try JSON first
        if content.startswith("{") or content.startswith("["):
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                raise ScenarioValidationError(f"Invalid JSON: {e}")
        
        # Simple YAML parser fallback (since pyyaml may not be installed/dependable)
        try:
            import yaml
            return yaml.safe_load(content)
        except ImportError:
            # Basic line-by-line YAML parser for simple schemas
            return self._parse_simple_yaml(content)
        except Exception as e:
            raise ScenarioValidationError(f"Failed to parse YAML: {e}")

    def _parse_simple_yaml(self, content: str) -> Dict[str, Any]:
        """Basic fallback YAML parser to support simple declarative scenarios."""
        result: Dict[str, Any] = {}
        current_steps: List[Dict[str, Any]] = []
        current_step: Optional[Dict[str, Any]] = None
        
        lines = content.splitlines()
        in_steps = False
        
        for line in lines:
            # Skip comments and empty lines
            if not line.strip() or line.strip().startswith("#"):
                continue
            
            indent = len(line) - len(line.lstrip())
            line_str = line.strip()
            
            if ":" not in line_str and not line_str.startswith("-"):
                continue
            
            if line_str.startswith("name:"):
                result["name"] = line_str.split(":", 1)[1].strip().strip('"\'')
            elif line_str.startswith("steps:"):
                in_steps = True
                result["steps"] = current_steps
            elif in_steps and line_str.startswith("-"):
                # New step
                current_step = {}
                current_steps.append(current_step)
                # Parse rest of line if key-value is on same line
                part = line_str[1:].strip()
                if ":" in part:
                    k, v = part.split(":", 1)
                    current_step[k.strip()] = self._parse_yaml_value(v.strip())
            elif in_steps and current_step is not None and ":" in line_str:
                k, v = line_str.split(":", 1)
                current_step[k.strip()] = self._parse_yaml_value(v.strip())
                
        if "steps" not in result:
            result["steps"] = current_steps
        return result

    def _parse_yaml_value(self, val: str) -> Any:
        val = val.strip().strip('"\'')
        if val.lower() == "true":
            return True
        if val.lower() == "false":
            return False
        if val.startswith("{") and val.endswith("}"):
            try:
                return json.loads(val)
            except Exception:
                pass
        return val

    def validate_scenario(self, scenario: Dict[str, Any]) -> None:
        """Validates scenario against the required schema."""
        if not isinstance(scenario, dict):
            raise ScenarioValidationError("Scenario must be a dictionary/object")
        
        if "name" not in scenario or not isinstance(scenario["name"], str):
            raise ScenarioValidationError("Scenario must have a string 'name'")
            
        if "steps" not in scenario or not isinstance(scenario["steps"], list):
            raise ScenarioValidationError("Scenario must have a list of 'steps'")
            
        for idx, step in enumerate(scenario["steps"]):
            if not isinstance(step, dict):
                raise ScenarioValidationError(f"Step at index {idx} must be an object")
            if "id" not in step or not isinstance(step["id"], str):
                raise ScenarioValidationError(f"Step at index {idx} missing string 'id'")
            if "action" not in step or not isinstance(step["action"], str):
                raise ScenarioValidationError(f"Step at index {idx} missing string 'action'")
            
            # params is optional but must be dict if present
            if "params" in step and not isinstance(step["params"], dict):
                raise ScenarioValidationError(f"Step '{step['id']}' 'params' must be a dictionary")
            
            # approval_required is optional but must be boolean
            if "approval_required" in step and not isinstance(step["approval_required"], bool):
                raise ScenarioValidationError(f"Step '{step['id']}' 'approval_required' must be a boolean")

    def _resolve_file_path(self, file_path: str) -> str:
        base = Path(self.vault_path or ".").resolve()
        candidate = Path(file_path)
        if not candidate.is_absolute():
            candidate = base / candidate
        resolved = candidate.resolve()
        if resolved != base and base not in resolved.parents:
            raise ScenarioValidationError(f"Scenario path is outside vault: {file_path}")
        return str(resolved)

    def _safe_eval_expression(self, expression: str) -> Any:
        """Evaluate simple constants, context names, booleans, and comparisons without eval()."""
        tree = ast.parse(expression, mode="eval")

        def eval_node(node):
            if isinstance(node, ast.Expression):
                return eval_node(node.body)
            if isinstance(node, ast.Constant):
                return node.value
            if isinstance(node, ast.Name):
                if node.id in self.context:
                    return self.context[node.id]
                raise ScenarioValidationError(f"Unknown scenario context name: {node.id}")
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                return not bool(eval_node(node.operand))
            if isinstance(node, ast.BoolOp):
                values = [bool(eval_node(value)) for value in node.values]
                if isinstance(node.op, ast.And):
                    return all(values)
                if isinstance(node.op, ast.Or):
                    return any(values)
            if isinstance(node, ast.Compare):
                left = eval_node(node.left)
                for op, comparator in zip(node.ops, node.comparators):
                    right = eval_node(comparator)
                    if isinstance(op, ast.Eq):
                        ok = left == right
                    elif isinstance(op, ast.NotEq):
                        ok = left != right
                    elif isinstance(op, ast.Lt):
                        ok = left < right
                    elif isinstance(op, ast.LtE):
                        ok = left <= right
                    elif isinstance(op, ast.Gt):
                        ok = left > right
                    elif isinstance(op, ast.GtE):
                        ok = left >= right
                    else:
                        raise ScenarioValidationError("Unsupported scenario comparison operator")
                    if not ok:
                        return False
                    left = right
                return True
            raise ScenarioValidationError("Unsupported scenario expression")

        return eval_node(tree)

    async def execute_step(self, step: Dict[str, Any], deps: Any) -> Dict[str, Any]:
        """Executes a single step in the scenario and returns status/outputs."""
        step_id = step["id"]
        action = step["action"]
        params = step.get("params", {})
        approval_required = step.get("approval_required", False)
        
        logger.info(f"Executing step {step_id}: {action} (approval_required={approval_required})")
        
        # Writes are always approval-gated when a UI callback is available.
        requires_approval = approval_required or action == "write_file"
        approval_callback = getattr(deps, "request_override", None)
        if requires_approval and not approval_callback:
            return {"status": "denied", "step_id": step_id, "error": "Approval callback is required for this action"}
        if requires_approval:
            approved = await approval_callback(f"Execute step {step_id}: {action} with params {params}")
            if not approved:
                return {"status": "denied", "step_id": step_id, "error": "Approval denied by security gate"}
        
        # Perform action
        # Here we mock or invoke real system tools based on dependency hooks
        output = {}
        status = "success"
        
        try:
            if action == "write_file":
                filepath = params.get("path")
                content = params.get("content", "")
                if filepath:
                    full_path = self._resolve_file_path(filepath)
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    output["bytes_written"] = len(content)
            elif action == "read_file":
                filepath = params.get("path")
                if filepath:
                    full_path = self._resolve_file_path(filepath)
                    with open(full_path, "r", encoding="utf-8") as f:
                        data = f.read()
                    output["content"] = data
            elif action == "evaluate_expression":
                expr = params.get("expression", "True")
                val = self._safe_eval_expression(expr)
                output["result"] = val
            elif action == "set_context":
                for k, v in params.items():
                    self.context[k] = v
                output["context_updated"] = True
            elif action == "conditional_route":
                condition = params.get("condition", "True")
                val = self._safe_eval_expression(condition)
                output["route_taken"] = params.get("if_true" if val else "if_false")
            else:
                # Custom mock implementation for other tools
                output["message"] = f"Mock action {action} completed successfully"
        except Exception as e:
            status = "error"
            output["error"] = str(e)
            
        result = {
            "status": status,
            "step_id": step_id,
            "output": output
        }
        self.history.append(result)
        
        # Merge step output into context
        self.context[f"step_{step_id}"] = output
        return result

    async def run_scenario(self, scenario_str: str, deps: Any) -> Dict[str, Any]:
        """Runs the entire scenario and returns the execution report."""
        scenario = self.parse_scenario(scenario_str)
        self.validate_scenario(scenario)
        
        self.context = {}
        self.history = []
        
        steps = scenario["steps"]
        step_map = {step["id"]: step for step in steps}
        
        current_step_idx = 0
        executed_steps = []
        
        while current_step_idx < len(steps):
            step = steps[current_step_idx]
            result = await self.execute_step(step, deps)
            executed_steps.append(result)
            
            if result["status"] == "denied":
                return {
                    "name": scenario["name"],
                    "status": "denied",
                    "failed_step": step["id"],
                    "history": executed_steps,
                    "context": self.context
                }
            elif result["status"] == "error":
                return {
                    "name": scenario["name"],
                    "status": "error",
                    "failed_step": step["id"],
                    "history": executed_steps,
                    "context": self.context
                }
                
            # Check for conditional routing
            next_step_id = result["output"].get("route_taken")
            if next_step_id:
                if next_step_id == "END":
                    break
                # Jump to step by ID
                found = False
                for idx, s in enumerate(steps):
                    if s["id"] == next_step_id:
                        current_step_idx = idx
                        found = True
                        break
                if not found:
                    return {
                        "name": scenario["name"],
                        "status": "error",
                        "failed_step": step["id"],
                        "error": f"Target route step '{next_step_id}' not found",
                        "history": executed_steps,
                        "context": self.context
                    }
            else:
                current_step_idx += 1
                
        return {
            "name": scenario["name"],
            "status": "success",
            "history": executed_steps,
            "context": self.context
        }
