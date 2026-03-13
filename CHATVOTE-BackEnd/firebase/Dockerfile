FROM node:20

# Firebase emulators require Java
RUN apt-get update -qq && \
    apt-get install -yqq --no-install-recommends default-jre-headless curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /firebase

# Copy config and install dependencies (baked into image for CI/Scaleway)
COPY package.json package-lock.json firebase.json firestore.rules firestore.indexes.json ./
RUN npm install

# Default: start both emulators (override via command for single-emulator mode)
CMD ["npx", "firebase", "emulators:start", "--project", "chat-vote-dev", "--only", "firestore,auth", "--host", "0.0.0.0"]
