Treat this project as if the target is a state-of-the-art application.

Instructions for Claude working in this repo. Project context (purpose, architecture, models, commands, cron, env vars) lives in `README.md` — read it before answering project-specific questions.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:

- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore

## Design System

Always read DESIGN.md before making any visual or UI decisions.
All font choices, colors, spacing, and aesthetic direction are defined there.
Do not deviate without explicit user approval.
In QA mode, flag any code that doesn't match DESIGN.md.

## Rules

### MUI Imports

Always import MUI components and icons individually — never use barrel imports:

```js
import Box from '@mui/material/Box';           // correct
import DeleteIcon from '@mui/icons-material/Delete';

import { Box } from '@mui/material';           // wrong
```

### Frontend colour selection

Never hardcode colours (e.g. `#ffffff`), instead always use the theme object provided by `frontend/src/styles/theme.js` (e.g. `background.default`, `text.secondary`). This ensures colour and contrast are respected by both light and dark mode.

### Database Schema Changes

Never edit migration files by hand. Notify the user and they will run:

```bash
uv run python manage.py makemigrations && uv run python manage.py migrate
```

### Code formatting

- Ruff is used as a python linter for python files within the backend/ directory:
    ```bash
    uv run ruff check . && uv run ruff format .
    ```

- Npm run lint is used as a JavaScript/TypeScript linter within the frontend/ directory:
    ```bash
    npm run lint
    ```

### Testing

Pytest for python files within the backend/ directory.

### Code Style

- **Python**: keep business logic in `utils/`, not in views
- **React**: functional components only; page-level state in the page component, props down

### Git Commit Messages

Commit messages are to be purely functional, briefly describing the changes to the code made for future git management. Don't write any other messaging (such as 'Co-authored by Claude').

## Boil the Ocean

The marginal cost of completeness is near zero with AI. Do the whole thing. Do it right. Do it with tests. Do it with documentation. Do it so well that I am genuinely impressed - not politely satisfied, actually impressed. Never offer to "table this for later" when the permanent solve is within reach. Never leave a dangling thread when tying it off takes five more minutes. Never present a workaround when the real fix exists. The standard isn't "good enough" - it's "holy shit, that's done." Search before building. Test before shipping. Ship the complete thing. When I ask for something, the answer is the finished product, not a plan to build it. Time is not an excuse. Fatigue is not an excuse. Complexity is not an excuse. Boil the ocean.

## Understanding project architecture

Project architecture is documented within [ARCHITECTURE.md](./ARCHITECTURE.md).
