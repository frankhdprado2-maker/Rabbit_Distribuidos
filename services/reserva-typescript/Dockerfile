FROM node:22.13.1-alpine AS build
WORKDIR /app
COPY package.json tsconfig.json ./
RUN npm install --ignore-scripts
COPY src src
RUN npm run build && npm prune --omit=dev
FROM node:22.13.1-alpine
WORKDIR /app
RUN addgroup -S app && adduser -S app -G app
COPY --from=build /app/node_modules node_modules
COPY --from=build /app/dist dist
USER app
EXPOSE 8082
CMD ["node","dist/index.js"]
