FROM node:22-alpine AS dev

WORKDIR /app

COPY frontend/package.json /app/package.json
COPY frontend/tsconfig.json /app/tsconfig.json
COPY frontend/tsconfig.app.json /app/tsconfig.app.json
COPY frontend/vite.config.ts /app/vite.config.ts
COPY frontend/eslint.config.js /app/eslint.config.js

RUN npm install

COPY frontend /app

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

FROM node:22-alpine AS build

WORKDIR /app

COPY frontend/package.json /app/package.json
COPY frontend/tsconfig.json /app/tsconfig.json
COPY frontend/tsconfig.app.json /app/tsconfig.app.json
COPY frontend/vite.config.ts /app/vite.config.ts
COPY frontend/eslint.config.js /app/eslint.config.js

RUN npm install

COPY frontend /app

ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN test -n "$VITE_API_BASE_URL" && \
    test "$VITE_API_BASE_URL" != "__MISSING_API_BASE_URL__"

RUN npm run build

FROM nginx:1.27-alpine AS prod

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
