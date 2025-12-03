"""Skill system for loading domain-specific prompts and capabilities.

Skills are defined in .arche/skills/{skill_name}/skill.yaml and contain:
- name: Skill identifier
- description: Human-readable description
- system_prompt: Additional system prompt for this skill
- tools: Optional list of tools the skill requires
- examples: Optional usage examples
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class SkillDefinition:
    """Complete skill definition from YAML."""
    name: str
    description: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    examples: list[dict] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "examples": self.examples,
            "metadata": self.metadata,
        }


@dataclass
class SkillInfo:
    """Lightweight skill info for listing."""
    name: str
    description: str
    path: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "path": self.path,
        }


class SkillLoader:
    """Loads and manages skills from .arche/skills/ directory.

    Skills provide domain-specific knowledge and capabilities through:
    - Custom system prompts that guide behavior
    - Tool recommendations
    - Usage examples
    """

    def __init__(self, arche_dir: Path):
        """Initialize skill loader.

        Args:
            arche_dir: Path to .arche directory
        """
        self.arche_dir = arche_dir
        self.skills_dir = arche_dir / "skills"
        self._cache: dict[str, SkillDefinition] = {}
        logger.info(f"SkillLoader initialized at {self.skills_dir}")

    def ensure_skills_dir(self) -> None:
        """Ensure skills directory exists."""
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def discover_skills(self) -> list[SkillInfo]:
        """Discover available skills.

        Returns:
            List of skill info for available skills
        """
        skills: list[SkillInfo] = []

        if not self.skills_dir.exists():
            return skills

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_yaml = skill_dir / "skill.yaml"
            if not skill_yaml.exists():
                # Try skill.yml
                skill_yaml = skill_dir / "skill.yml"
                if not skill_yaml.exists():
                    continue

            try:
                with open(skill_yaml) as f:
                    data = yaml.safe_load(f)

                if data:
                    skills.append(SkillInfo(
                        name=data.get("name", skill_dir.name),
                        description=data.get("description", ""),
                        path=str(skill_dir),
                    ))
            except Exception as e:
                logger.warning(f"Failed to load skill from {skill_yaml}: {e}")
                continue

        # Sort by name
        skills.sort(key=lambda s: s.name)
        return skills

    def load_skill(self, name: str) -> SkillDefinition | None:
        """Load a skill by name.

        Args:
            name: Skill name (directory name)

        Returns:
            SkillDefinition if found, None otherwise
        """
        # Check cache
        if name in self._cache:
            return self._cache[name]

        skill_dir = self.skills_dir / name
        if not skill_dir.exists():
            logger.warning(f"Skill directory not found: {skill_dir}")
            return None

        # Try both .yaml and .yml
        skill_yaml = skill_dir / "skill.yaml"
        if not skill_yaml.exists():
            skill_yaml = skill_dir / "skill.yml"
            if not skill_yaml.exists():
                logger.warning(f"Skill YAML not found in {skill_dir}")
                return None

        try:
            with open(skill_yaml) as f:
                data = yaml.safe_load(f)

            if not data:
                return None

            skill = SkillDefinition(
                name=data.get("name", name),
                description=data.get("description", ""),
                system_prompt=data.get("system_prompt", ""),
                tools=data.get("tools", []),
                examples=data.get("examples", []),
                metadata=data.get("metadata", {}),
            )

            # Cache it
            self._cache[name] = skill
            logger.info(f"Loaded skill: {name}")
            return skill

        except Exception as e:
            logger.error(f"Failed to load skill {name}: {e}")
            return None

    def get_skill_prompt(self, name: str) -> str:
        """Get system prompt for a skill.

        Args:
            name: Skill name

        Returns:
            System prompt or empty string if not found
        """
        skill = self.load_skill(name)
        return skill.system_prompt if skill else ""

    def get_combined_prompt(self, skill_names: list[str]) -> str:
        """Get combined system prompt for multiple skills.

        Args:
            skill_names: List of skill names to combine

        Returns:
            Combined system prompt with skill sections
        """
        prompts = []

        for name in skill_names:
            skill = self.load_skill(name)
            if skill and skill.system_prompt:
                prompts.append(f"# Skill: {skill.name}\n\n{skill.system_prompt}")

        return "\n\n---\n\n".join(prompts)

    def get_skill_tools(self, name: str) -> list[str]:
        """Get recommended tools for a skill.

        Args:
            name: Skill name

        Returns:
            List of tool names
        """
        skill = self.load_skill(name)
        return skill.tools if skill else []

    def clear_cache(self) -> None:
        """Clear the skill cache."""
        self._cache.clear()

    def reload_skill(self, name: str) -> SkillDefinition | None:
        """Reload a skill from disk.

        Args:
            name: Skill name to reload

        Returns:
            Reloaded skill definition
        """
        if name in self._cache:
            del self._cache[name]
        return self.load_skill(name)

    def create_skill(
        self,
        name: str,
        description: str,
        system_prompt: str,
        tools: list[str] | None = None,
        examples: list[dict] | None = None,
    ) -> SkillDefinition | None:
        """Create a new skill.

        Args:
            name: Skill name (will be used as directory name)
            description: Human-readable description
            system_prompt: System prompt content
            tools: Optional list of recommended tools
            examples: Optional usage examples

        Returns:
            Created skill definition
        """
        self.ensure_skills_dir()

        # Sanitize name for directory
        safe_name = "".join(c for c in name if c.isalnum() or c in "-_").lower()
        skill_dir = self.skills_dir / safe_name

        if skill_dir.exists():
            logger.error(f"Skill directory already exists: {skill_dir}")
            return None

        try:
            skill_dir.mkdir(parents=True)

            skill_data = {
                "name": name,
                "description": description,
                "system_prompt": system_prompt,
            }
            if tools:
                skill_data["tools"] = tools
            if examples:
                skill_data["examples"] = examples

            skill_yaml = skill_dir / "skill.yaml"
            with open(skill_yaml, "w") as f:
                yaml.dump(skill_data, f, default_flow_style=False, allow_unicode=True)

            logger.info(f"Created skill: {name}")
            return self.load_skill(safe_name)

        except Exception as e:
            logger.error(f"Failed to create skill {name}: {e}")
            return None

    def delete_skill(self, name: str) -> bool:
        """Delete a skill.

        Args:
            name: Skill name

        Returns:
            True if deleted successfully
        """
        skill_dir = self.skills_dir / name
        if not skill_dir.exists():
            return False

        try:
            import shutil
            shutil.rmtree(skill_dir)

            # Clear from cache
            if name in self._cache:
                del self._cache[name]

            logger.info(f"Deleted skill: {name}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete skill {name}: {e}")
            return False


# Built-in skill templates that can be installed
BUILTIN_SKILLS = {
    "code-review": {
        "name": "Code Review",
        "description": "Expert code reviewer analyzing code quality, patterns, and best practices",
        "system_prompt": """You are an expert code reviewer with deep knowledge of software engineering best practices.

## Your Responsibilities
1. **Code Quality**: Analyze code for clarity, maintainability, and efficiency
2. **Best Practices**: Identify violations of language-specific conventions and patterns
3. **Security**: Flag potential security vulnerabilities
4. **Performance**: Spot performance issues and optimization opportunities
5. **Architecture**: Evaluate design patterns and architectural decisions

## Review Process
1. First, read the code to understand its purpose
2. Analyze structure, naming, and organization
3. Check for common issues (null handling, error handling, edge cases)
4. Look for security concerns
5. Consider testability and documentation
6. Provide specific, actionable feedback

## Output Format
Organize findings by severity:
- 🔴 **Critical**: Must fix - security issues, bugs, data loss risks
- 🟡 **Important**: Should fix - performance, maintainability issues
- 🔵 **Suggestion**: Nice to have - style improvements, refactoring ideas

Always explain *why* something is an issue and suggest how to fix it.""",
        "tools": ["read_file", "glob", "grep"],
    },
    "web-research": {
        "name": "Web Research",
        "description": "Research assistant for gathering and synthesizing web information",
        "system_prompt": """You are an expert web researcher skilled at finding, evaluating, and synthesizing information.

## Research Methodology
1. **Understand the Query**: Clarify what information is needed
2. **Search Strategy**: Plan effective search queries
3. **Source Evaluation**: Assess credibility and relevance
4. **Information Synthesis**: Combine findings into coherent insights
5. **Citation**: Always provide sources for information

## Quality Standards
- Prioritize authoritative sources (official docs, academic papers, established publications)
- Cross-reference claims across multiple sources
- Note when information conflicts or is uncertain
- Distinguish between facts, expert opinions, and speculation

## Output Format
Structure research findings with:
- Executive summary (2-3 sentences)
- Key findings (bulleted list)
- Detailed analysis
- Sources and citations
- Areas of uncertainty or further research needed""",
        "tools": ["web_search", "web_fetch"],
    },
    "refactoring": {
        "name": "Refactoring Expert",
        "description": "Code refactoring specialist focused on improving code structure",
        "system_prompt": """You are an expert code refactoring specialist with deep knowledge of design patterns and clean code principles.

## Refactoring Principles
1. **Preserve Behavior**: Refactoring must not change external behavior
2. **Small Steps**: Make incremental changes that are easy to verify
3. **Test Coverage**: Ensure tests exist before refactoring
4. **Clear Intent**: Each change should have a clear purpose

## Common Refactoring Patterns
- Extract Method/Function
- Rename for clarity
- Move to appropriate module/class
- Replace conditionals with polymorphism
- Introduce parameter objects
- Replace magic numbers with constants
- Simplify complex conditionals

## Process
1. Understand the current code structure
2. Identify code smells and improvement opportunities
3. Plan refactoring steps
4. Execute changes incrementally
5. Verify tests pass after each step

## Output Format
For each refactoring suggestion:
1. **What**: Describe the change
2. **Why**: Explain the benefit
3. **Before/After**: Show code examples
4. **Risk**: Note any potential issues""",
        "tools": ["read_file", "edit_file", "glob", "grep"],
    },
    "debugging": {
        "name": "Debugging Expert",
        "description": "Systematic debugger for tracking down and fixing bugs",
        "system_prompt": """You are an expert debugger skilled at systematically tracking down and fixing bugs.

## Debugging Methodology
1. **Reproduce**: First confirm the bug and understand reproduction steps
2. **Isolate**: Narrow down where the bug occurs
3. **Understand**: Comprehend the code's intended behavior
4. **Hypothesize**: Form theories about the cause
5. **Test**: Verify hypotheses with targeted investigation
6. **Fix**: Implement the minimal change that fixes the issue
7. **Verify**: Confirm the fix works and doesn't break anything else

## Investigation Techniques
- Read error messages and stack traces carefully
- Add logging/print statements strategically
- Use binary search to narrow down problem areas
- Check recent changes (git blame, git log)
- Review related tests
- Consider edge cases and boundary conditions

## Common Bug Categories
- Off-by-one errors
- Null/undefined handling
- Race conditions
- State management issues
- Type coercion problems
- Resource leaks
- Logic errors in conditionals

## Output Format
1. **Bug Analysis**: What's happening vs what should happen
2. **Root Cause**: Why it's happening
3. **Fix**: Code changes needed
4. **Prevention**: How to avoid similar bugs""",
        "tools": ["read_file", "grep", "glob", "execute"],
    },
}


def install_builtin_skills(arche_dir: Path) -> int:
    """Install built-in skills to .arche/skills/ directory.

    Args:
        arche_dir: Path to .arche directory

    Returns:
        Number of skills installed
    """
    loader = SkillLoader(arche_dir)
    loader.ensure_skills_dir()

    installed = 0
    for skill_id, skill_data in BUILTIN_SKILLS.items():
        skill_dir = loader.skills_dir / skill_id
        if skill_dir.exists():
            continue  # Don't overwrite existing

        result = loader.create_skill(
            name=skill_data["name"],
            description=skill_data["description"],
            system_prompt=skill_data["system_prompt"],
            tools=skill_data.get("tools"),
        )
        if result:
            installed += 1

    return installed
