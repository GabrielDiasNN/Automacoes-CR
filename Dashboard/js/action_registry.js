const handlers = new Map();

export function registerAction(name, handler) {
    handlers.set(name, handler);
}

export function bindActionElements(root = document) {
    root.querySelectorAll("[data-action]").forEach((element) => {
        const eventName = element.dataset.actionEvent || "click";
        const bindingKey = `${element.dataset.action || ""}:${eventName}`;
        if (element.dataset.actionBound === bindingKey) return;
        const actionName = element.dataset.action;
        element.addEventListener(eventName, (event) => {
            const handler = handlers.get(actionName);
            if (!handler) return;
            handler(event, element);
        });
        element.dataset.actionBound = bindingKey;
    });
}
