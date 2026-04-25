from typing import Dict, Any, List
from .schemas import WorkflowDefinitionV2, WorkflowNodeV2, NodeType
from .event_bus import event_bus, Event
from ...logs.logger import logger

class WorkflowEngineV2:
    async def execute(self, workflow: WorkflowDefinitionV2, initial_context: Dict[str, Any], dry_run: bool = False):
        logger.info(f"[WorkflowV2] Starting workflow {workflow.workflow_id} (dry_run={dry_run})")
        await event_bus.publish(f"workflow:{workflow.workflow_id}", Event("workflow.started", {"workflow_id": workflow.workflow_id, "dry_run": dry_run}))
        
        graph: Dict[str, List[str]] = {n.node_id: [] for n in workflow.nodes}
        for edge in workflow.edges:
            if edge.from_node in graph:
                graph[edge.from_node].append(edge.to_node)
        
        node_map = {n.node_id: n for n in workflow.nodes}
        completed = set()
        failed = set()
        context = dict(initial_context)
        path_taken: List[str] = []
        decisions: List[Dict[str, Any]] = []
        estimated_tokens = 0
        
        all_targets = {e.to_node for e in workflow.edges}
        entry_nodes = [n for n in workflow.nodes if n.node_id not in all_targets]
        queue = [n.node_id for n in entry_nodes]
        
        while queue:
            node_id = queue.pop(0)
            if node_id in completed or node_id in failed:
                continue
            
            node = node_map.get(node_id)
            if not node:
                continue
            
            path_taken.append(node_id)
            await event_bus.publish(f"workflow:{workflow.workflow_id}", Event("node.started", {"node_id": node_id, "dry_run": dry_run}))
            
            try:
                result = await self._execute_node(node, context, dry_run)
                context[node_id] = result
                completed.add(node_id)
                estimated_tokens += result.get("estimated_tokens", 0)
                if node.type == NodeType.DECISION:
                    decisions.append({
                        "node_id": node_id,
                        "condition": node.condition,
                        "result": result.get("decision_result", True),
                    })
                await event_bus.publish(f"workflow:{workflow.workflow_id}", Event("node.completed", {"node_id": node_id, "result": result, "dry_run": dry_run}))
                
                for next_id in graph.get(node_id, []):
                    if next_id not in queue and next_id not in completed:
                        queue.append(next_id)
            except Exception as e:
                logger.error(f"[WorkflowV2] Node {node_id} failed: {e}")
                failed.add(node_id)
                await event_bus.publish(f"workflow:{workflow.workflow_id}", Event("node.failed", {"node_id": node_id, "error": str(e), "dry_run": dry_run}))
        
        await event_bus.publish(f"workflow:{workflow.workflow_id}", Event("workflow.completed", {"completed": list(completed), "failed": list(failed), "dry_run": dry_run}))
        
        if dry_run:
            return {
                "context": context,
                "completed": list(completed),
                "failed": list(failed),
                "path": path_taken,
                "decisions": decisions,
                "estimated_tokens": estimated_tokens,
            }
        return {"context": context, "completed": list(completed), "failed": list(failed)}
    
    async def _execute_node(self, node: WorkflowNodeV2, context: Dict[str, Any], dry_run: bool = False) -> Any:
        if dry_run:
            if node.type == NodeType.AGENT:
                return {"agent_id": node.agent_id, "agent_name": node.agent_id or "unknown", "status": "dry_run", "estimated_tokens": 150}
            elif node.type == NodeType.TOOL:
                return {"tool_bindings": node.tool_bindings, "status": "dry_run", "estimated_tokens": 50}
            elif node.type == NodeType.DECISION:
                # In dry run, evaluate condition if possible, else assume True
                try:
                    if node.condition:
                        result = eval(node.condition, {"context": context, "__builtins__": {}})
                    else:
                        result = True
                except Exception:
                    result = True
                return {"condition": node.condition, "status": "dry_run", "decision_result": bool(result), "estimated_tokens": 10}
            elif node.type == NodeType.WAIT:
                return {"status": "dry_run", "estimated_tokens": 0}
            else:
                return {"status": "dry_run", "estimated_tokens": 0}
        
        if node.type == NodeType.AGENT:
            from ...agents.v2.registry import agent_registry_v2
            agent = await agent_registry_v2.get(node.agent_id) if node.agent_id else None
            agent_name = agent.name if agent else "unknown"
            return {"agent_id": node.agent_id, "agent_name": agent_name, "status": "executed"}
        elif node.type == NodeType.TOOL:
            return {"tool_bindings": node.tool_bindings, "status": "executed"}
        elif node.type == NodeType.DECISION:
            return {"condition": node.condition, "status": "evaluated"}
        elif node.type == NodeType.WAIT:
            return {"status": "waiting_approval"}
        else:
            return {"status": "unknown_node_type"}

workflow_engine_v2 = WorkflowEngineV2()
