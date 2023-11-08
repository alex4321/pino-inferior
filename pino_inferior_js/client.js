class PIRequestParams {
    constructor(id) {
        this.id = id;
    }

    toDict() {
        return {
            "id": this.id
        }
    }

    toJSON() {
        return JSON.stringify(this.toDict());
    }
}


class PIUserDescription {
    constructor(name, character, goals) {
        this.name = name;
        this.character = character;
        this.goals = goals;
    }

    toDict() {
        return {
            "name": this.name,
            "character": this.character,
            "goals": this.goals
        }
    }
}


class PIUserDescriptionWithStyle extends PIUserDescription {
    constructor(name, character, goals, styleExamples, styleDescription) {
        super(name, character, goals);
        this.styleExamples = styleExamples;
        this.styleDescription = styleDescription;
    }

    toDict() {
        let result = super.toDict();
        result["style_examples"] = this.styleExamples;
        result["style_description"] = this.styleDescription;
        return result;
    }
}


class PIMessage {
    constructor(author, time, content) {
        this.author = author;
        this.time = time;
        this.content = content;
    }

    toDict() {
        return {
            "author": this.author,
            "time": this.time,
            "content": this.content,
        };
    }
}


class PICommentRequestParams extends PIRequestParams {
    constructor(id, context, history, user) {
        super(id);
        this.context = context;
        this.history = history;
        this.user = user;
    }

    toDict() {
        let result = super.toDict();
        result["context"] = this.context;
        result["history"] = this.history.map((message) => message.toDict());
        result["user"] = this.user.toDict();
        return result;
    }

    toJSON() {
        return super.toJSON();
    }
}


class APIResponse {
    constructor(properties) {
        this.sessionId = properties.id;
        this.callbackSystem = properties.callbackSystem;
        this.callbackType = properties.callbackType;
        this.time = properties.time;
        this.response = properties.response;
    }
}


class PIClientInsides {
    constructor(websocketHostUrl) {
        this.websocket = new WebSocket(websocketHostUrl);
        this.sessionQueryCounter = 0;
        this.sessionCallbacks = {};
        this.onConnectionOpen = null;
        this.onConnectionError = null;
        this.onConnectionClose = null;
        let client = this;
        this.websocket.onopen = function (event) {
            if (client.onConnectionOpen) {
                client.onConnectionOpen();
            }
        }
        this.websocket.onerror = function (event) {
            if (client.onConnectionError) {
                client.onConnectionError();
            }
        };
        this.websocket.onclose = function (event) {
            if (client.onConnectionClose) {
                client.onConnectionClose();
            }
        };
        this.websocket.onmessage = function (event) {
            let response = new APIResponse(JSON.parse(event.data));
            let sessionId = response.sessionId;
            if (client.sessionCallbacks[sessionId]) {
                client.sessionCallbacks[sessionId](response);
            }
        }
    }

    registerSessionCallback(sessionId, callback) {
        this.sessionCallbacks[sessionId] = callback;
    }

    unRegisterSessionCallnack(sessionId) {
        delete this.sessionCallbacks[sessionId];
    }

    sendQuery(queryType, queryParams, callback) {
        this.sessionQueryCounter++;
        let queryId = this.sessionQueryCounter;
        this.registerSessionCallback(queryId, callback);
        let queryMessage = queryType + " " + queryParams.toJSON();
        this.websocket.send(queryMessage);
        return queryId;
    }
}
