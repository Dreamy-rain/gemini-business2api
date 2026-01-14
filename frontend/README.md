# Frontend - Admin Panel

Modern admin panel built with Vue 3 + TypeScript + Tailwind CSS.

## Tech Stack

- Vue 3 + TypeScript
- Vite
- Vue Router + Pinia
- Tailwind CSS
- Axios
- ECharts

## Development

```bash
# Install dependencies
npm install

# Start dev server
npm run dev
```

Visit: http://localhost:5174

## Build

```bash
# Build for production
npm run build

# Preview build
npm run preview
```

Build output: `dist/`

## Project Structure

```
src/
├── api/          # API requests
├── components/   # UI components
├── views/        # Page components
├── stores/       # Pinia stores
├── router/       # Vue Router
└── types/        # TypeScript types
```

## Environment Variables

Create `.env.local`:

```bash
VITE_API_BASE_URL=http://localhost:7860
```

## Docker Build

The root `Dockerfile` automatically builds the frontend:

```dockerfile
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
```

Build artifacts are copied to `static/` directory.