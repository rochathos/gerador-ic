from typing import List, Dict, Any, Optional
from collections import defaultdict
from sqlalchemy.orm import Session
from app.core.logger import logger
from app.models.commit import Commit
from app.models.meeting import Meeting
from app.models.catalog_item import CatalogItem


class CatalogGeneratorService:
    """Analyzes commits and meetings to group them and suggest Catalog Items (ICs)."""

    @classmethod
    def group_commits(cls, commits: List[Commit]) -> Dict[str, List[Commit]]:
        """Group related commits using keywords, files changed, or branches."""
        groups: Dict[str, List[Commit]] = defaultdict(list)

        for commit in commits:
            msg_lower = commit.message.lower()

            # Categorization heuristic
            if any(k in msg_lower for k in ["fix", "correc", "corrige", "bug", "erro"]):
                category = "Correções e Ajustes"
            elif any(k in msg_lower for k in ["feat", "adiciona", "novo", "implementa", "criac"]):
                category = "Novas Funcionalidades"
            elif any(k in msg_lower for k in ["refactor", "melhoria", "otimiz", "ajuste"]):
                category = "Melhorias Técnicas e Refatoração"
            elif any(k in msg_lower for k in ["docs", "doc", "documenta"]):
                category = "Documentação"
            elif any(k in msg_lower for k in ["test", "teste"]):
                category = "Testes Automatizados"
            else:
                category = "Atividades Gerais de Desenvolvimento"

            groups[category].append(commit)

        return dict(groups)

    @classmethod
    def generate_suggestions(
        cls,
        commits: List[Commit],
        meetings: Optional[List[Meeting]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate Catalog Item proposals with synthesized descriptions."""
        if not commits and not meetings:
            return []

        logger.info(f"Gerando sugestões de ICs para {len(commits)} commits...")
        grouped = cls.group_commits(commits)
        suggestions: List[Dict[str, Any]] = []

        for category, cat_commits in grouped.items():
            commit_messages = [c.message.split("\n")[0] for c in cat_commits]
            title = f"{category} - {commit_messages[0][:60]}"

            # Generate consolidated description
            description_lines = [
                f"Atividades realizadas no período compreendendo {len(cat_commits)} commits relacionados:",
                "",
                "Detalhamento dos commits:",
            ]
            for c in cat_commits:
                description_lines.append(f"- [{c.short_hash}] {c.message}")

            if cat_commits:
                all_files = set()
                for c in cat_commits:
                    if isinstance(c.files_changed, list):
                        all_files.update(c.files_changed)
                if all_files:
                    description_lines.append("")
                    description_lines.append(f"Arquivos impactados: {len(all_files)}")

            description = "\n".join(description_lines)

            suggestions.append(
                {
                    "title": title,
                    "description": description,
                    "status": "sugerido",
                }
            )

        return suggestions

    @classmethod
    def save_suggestions(
        cls,
        db: Session,
        suggestions: List[Dict[str, Any]],
        execution_id: Optional[int] = None,
    ) -> List[CatalogItem]:
        """Save generated Catalog Items into the database."""
        created_items: List[CatalogItem] = []
        try:
            for s in suggestions:
                item = CatalogItem(
                    title=s["title"],
                    description=s["description"],
                    status=s.get("status", "sugerido"),
                    execution_id=execution_id,
                )
                db.add(item)
                created_items.append(item)
            db.commit()
            for item in created_items:
                db.refresh(item)
            logger.info(f"{len(created_items)} sugestões de ICs salvas no PostgreSQL.")
            return created_items
        except Exception as exc:
            db.rollback()
            logger.error(f"Erro ao salvar sugestões de IC: {exc}")
            raise
