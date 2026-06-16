import re
from typing import List, Dict, Any

class ContextCondenser:
    """
    ContextCondenser dynamically compresses message history context.
    It protects the head (e.g., system prompt and first user message) 
    and the tail (recent messages) while summarizing/folding the middle.
    """
    def __init__(self, max_chars: int = 4000, head_count: int = 1, tail_count: int = 3):
        self.max_chars = max_chars
        self.head_count = head_count
        self.tail_count = tail_count

    def condense_context(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Condenses the message list if the total character length of message contents exceeds max_chars.
        """
        if not messages:
            return []
            
        total_len = sum(len(str(m.get("content", ""))) for m in messages)
        if total_len <= self.max_chars:
            return messages

        # Protect head and tail
        if len(messages) <= (self.head_count + self.tail_count):
            # Too few messages to condense the middle, perform individual compression on messages
            condensed = []
            for m in messages:
                condensed.append({
                    "role": m["role"],
                    "content": self.compress_single_message(m.get("content", ""))
                })
            return condensed

        head_messages = messages[:self.head_count]
        tail_messages = messages[-self.tail_count:] if self.tail_count > 0 else []
        middle_messages = messages[self.head_count:-self.tail_count] if self.tail_count > 0 else messages[self.head_count:]

        # Condense the middle messages into a single summary message
        summarized_middle = self.summarize_middle(middle_messages)

        return head_messages + [summarized_middle] + tail_messages

    def compress_single_message(self, content: str) -> str:
        """
        Compresses a single long message by folding code blocks 
        and keeping only the key parts.
        """
        if not content:
            return ""
            
        # Fold code blocks
        def code_folder(match):
            lang = match.group(1) or ""
            code = match.group(2)
            lines = code.splitlines()
            if len(lines) > 10:
                folded_code = "\n".join(lines[:3]) + f"\n... [FOLDED {len(lines) - 6} LINES] ...\n" + "\n".join(lines[-3:])
                return f"```{lang}\n{folded_code}```"
            return match.group(0)

        folded_content = re.sub(r"```(\w*)\n(.*?)```", code_folder, content, flags=re.DOTALL)
        
        # If still too long, keep first 500 and last 500 chars
        if len(folded_content) > 2000:
            return folded_content[:1000] + "\n\n... [TRUNCATED HIGH-VOLUME CONTENT] ...\n\n" + folded_content[-1000:]
        return folded_content

    def summarize_middle(self, middle_messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Summarizes a group of middle messages.
        It extracts roles, key sentences, and statistics.
        """
        total_msgs = len(middle_messages)
        roles_involved = set(m.get("role") for m in middle_messages)
        
        # Collect text fragments
        fragments = []
        for idx, m in enumerate(middle_messages):
            role = m.get("role", "unknown")
            content = str(m.get("content", ""))
            
            # Extract first line or clean sentences
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            first_line = lines[0] if lines else ""
            if len(first_line) > 100:
                first_line = first_line[:97] + "..."
                
            fragments.append(f"- {role}: {first_line}")
            
        summary_content = (
            f"=== [CONTEXT CONDENSER SUMMARY: {total_msgs} messages folded ({', '.join(roles_involved)})] ===\n"
            + "\n".join(fragments[:15]) # Limit to 15 key points
        )
        if len(fragments) > 15:
            summary_content += f"\n... and {len(fragments) - 15} more folded events."
            
        return {
            "role": "system",
            "content": summary_content
        }
