FROM docker.io/library/node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM docker.io/library/nginx:1.27-alpine
# The image renders templates/*.template into conf.d/ at startup; this flag fills
# in NGINX_LOCAL_RESOLVERS with the container's DNS server.
ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
COPY first-resolver.envsh /docker-entrypoint.d/16-first-resolver.envsh
RUN chmod +x /docker-entrypoint.d/16-first-resolver.envsh
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
