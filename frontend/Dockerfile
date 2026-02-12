# Frontend Dockerfile
FROM node:22-alpine

WORKDIR /app

# Install dependencies (cache based on package.json)
COPY package.json package-lock.json ./
RUN npm ci

# Copy source
COPY . .

# Build
RUN npm run build

# Dev mode for now to keep proxy working
CMD ["npm", "run", "dev", "--", "--host"]

# Expose port
EXPOSE 5173
