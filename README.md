# Template — Django + React Stack

This template is a Django backend + React frontend, made to run locally and deploy to a self-hosted Linux homeserver. Each branch is a complete, working project you can clone and build on directly.

---

> **NOTE:** This `main` branch serves as the repository landing page and navigation guide. The actual starter templates live on dedicated branches — pick the one matching your OS and feature requirements below.

---

## Architecture Overview

```
+----------------------------------------------------------+
|                      React PWA                           |
|      Frontend: Auth, Dark Mode, Protected Routes         |
+----------------------------+-----------------------------+
                             | REST API / JSON
+----------------------------v-----------------------------+
|                 Django REST Framework                    |
|      Backend: Auth, DB Schema, API Endpoints             |
+--------------+---------------------------+---------------+
               |                           |
   (Base Variant)                  (LLM Variant)
+--------------v----------+    +-----------v---------------+
|  Docker Container Stack |    |   LLM Harness & MCP       |
|  Homeserver Deployment  |    |   Chat UI & Tool Server   |
+-------------------------+    +---------------------------+
```

## Choose Your Template Branch

Templates are structured as `template/<os>/<variant>`. Select the branch tailored to your host OS and project scope:


| Target OS         | Stack Variant        | Branch Name                                     | Direct Link                                                               |
| ----------------- | -------------------- | ----------------------------------------------- | ------------------------------------------------------------------------- |
| **macOS / Linux** | **Base Web App**     | `template/mac/react-django-web-app`             | [Browse Branch](../../tree/template/mac/react-django-web-app)             |
| **macOS / Linux** | **Base + LLM + MCP** | `template/mac/react-django-llm-harness-mcp`     | [Browse Branch](../../tree/template/mac/react-django-llm-harness-mcp)     |
| **Windows**       | **Base Web App**     | `template/windows/react-django-web-app`         | [Browse Branch](../../tree/template/windows/react-django-web-app)         |
| **Windows**       | **Base + LLM + MCP** | `template/windows/react-django-llm-harness-mcp` | [Browse Branch](../../tree/template/windows/react-django-llm-harness-mcp) |


## Feature Comparison


| Included Feature                        | Base Web App | Base + LLM + MCP |
| --------------------------------------- | ------------ | ---------------- |
| **Django REST Framework API**           | ✔️           | ✔️               |
| **React PWA with UI Theming**           | ✔️           | ✔️               |
| **Authentication & Protected Routes**   | ✔️           | ✔️               |
| **Dockerized Homeserver Pipeline**      | ✔️           | ✔️               |
| **Interactive LLM Chat Interface**      | —            | ✔️               |
| **Model Context Protocol (MCP) Server** | —            | ✔️               |
| **Agent Tool Exposure Layer**           | —            | ✔️               |


## Quick Start Workflow

```
+------------------+     +------------------+     +------------------+
|  1. Select       | --> |  2. Clone        | --> |  3. Configure    |
|  OS & Variant    |     |  Target Branch   |     |  Follow README   |
+------------------+     +------------------+     +------------------+
```

1. **Pick your target branch** from the selection table above.
2. **Clone the branch** directly into your new project directory:
  ```bash
   git clone -b <branch-name> https://github.com/KiddKailash/Template-React-Django my-app
   cd my-app
   git remote remove origin
  ```
3. **Open the branch** `README.md` — it guides you step-by-step through local setup, renaming the app, and deploying to production.

## Repository Layout

```
main (Landing Page & Documentation)
 |-- template/
      |-- mac/
      |    |-- react-django-web-app            # Base macOS/Linux stack
      |    |-- react-django-llm-harness-mcp    # AI-extended macOS/Linux stack
      |-- windows/
           |-- react-django-web-app            # Base Windows stack
           |-- react-django-llm-harness-mcp    # AI-extended Windows stack
```

> **TIP:** Treat these template branches as long-lived upstream sources. Pull from them whenever starting a new project.

