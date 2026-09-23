# InsightFlow

InsightFlow est un espace de travail contrôlé pour l’analyse métier, construit sur le runtime d’agents de DeerFlow v2.1.0-rc0. Le dépôt conserve la licence MIT et les mentions de copyright en amont. Consultez [LICENSE](LICENSE) et le projet amont [DeerFlow](https://github.com/bytedance/deer-flow).

## Fonctionnalités

- Analyses gouvernées des sources de données enregistrées, indicateurs, rapports et historique d’audit.
- Analyses par conversation avec réponses en flux, artefacts, tâches de sous-agents ordinaires et exécutions planifiées.
- Recherche Web limitée à DuckDuckGo et à la récupération Jina.
- Serveurs MCP et compétences administrés par l’opérateur ; SkillScan vérifie les compétences installées.
- Modes de sandbox Local et AIO pour les outils de fichiers et de commandes.

L’interface comprend l’analyse, les conversations, les sources de données, les indicateurs, les rapports, l’historique et les tâches planifiées. Les ponts IM supprimés, l’éditeur Custom Agent, les pages projets/documents/corbeille et le contrôle interactif du navigateur n’en font pas partie.

## Démarrage rapide

Prérequis : Docker Compose, Python 3.12+, Node.js 22+, uv et pnpm 10.26.2+.

1. Créez la configuration locale et installez les dépendances :

   ~~~sh
   make config
   make install
   ~~~

2. Modifiez config.yaml, ignoré par Git, et configurez au moins un modèle sous models. Gardez les clés comme OPENAI_API_KEY ou DEEPSEEK_API_KEY dans l’environnement.
3. Démarrez l’environnement de développement :

   ~~~sh
   make dev
   ~~~

Ouvrez http://localhost:2026. Le port Nginx publié est lié à l’interface locale par défaut. Utilisez make start pour le mode local optimisé et make up pour la pile Docker de production.

Ne validez pas config.yaml, extensions_config.json, .env ni les identifiants des fournisseurs. Consultez la [configuration](backend/docs/CONFIGURATION.md) et le [guide d’installation](Install.md).

## Limites Analytics et Agent

Les requêtes Analytics passent par le service de requêtes gouverné : les identifiants des sources restent côté serveur, les plans sont autorisés avant exécution et l’historique d’audit est conservé. Les outils Agent ne contournent pas ce service.

Le Lead Agent délègue des tâches ordinaires aux sous-agents intégrés. Les exécutions planifiées suivent le cycle de vie Gateway standard. Les commandes du sandbox Local utilisent les privilèges de l’hôte Gateway ; AIO utilise un service séparé. Un provisioner AIO externe est uniquement une adresse cliente configurée : ce dépôt ne fournit ni ne démarre ce service.

Considérez les serveurs MCP, extensions, fournisseurs de modèles et destinations sandbox comme des services de confiance. N’exposez pas directement le Gateway à un réseau non fiable.

## Développement

~~~sh
make check
cd backend
make test
make lint
cd ../frontend
pnpm check
pnpm test
pnpm test:e2e
~~~

La suite backend par défaut fonctionne hors ligne ; les tests de fournisseurs réels doivent être activés explicitement. Consultez le [guide backend](backend/AGENTS.md), le [guide frontend](frontend/AGENTS.md) et les [scénarios d’acceptation](docs/acceptance/acceptance-scenarios.md).

## Licence et attribution

Ce dépôt dérive de DeerFlow v2.1.0-rc0 et conserve sa licence MIT ainsi que les mentions de copyright. Les modifications propres à InsightFlow sont maintenues ici. Voir [LICENSE](LICENSE).
