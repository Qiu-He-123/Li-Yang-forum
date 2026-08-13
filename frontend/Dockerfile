FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
# 反爬：nginx-ultimate-bad-bot-blocker（http 级 map/限流区 + server 级生效文件）
COPY ngxblocker/conf.d/botblocker-nginx-settings.conf /etc/nginx/conf.d/10-botblocker-settings.conf
COPY ngxblocker/conf.d/globalblacklist.conf /etc/nginx/conf.d/20-botblocker.conf
COPY nginx-ratelimit.conf /etc/nginx/conf.d/30-ratelimit.conf
COPY nginx-security-headers.conf /etc/nginx/conf.d/40-security-headers.conf
COPY ngxblocker/bots.d /etc/nginx/bots.d
COPY ngxblocker/LICENSE.md /etc/nginx/ngxblocker-LICENSE.md
# 构建期校验 nginx 配置，语法错误直接构建失败
RUN nginx -t
EXPOSE 80
