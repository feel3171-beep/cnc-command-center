let _prisma: any = null;

function getPrisma() {
  if (!_prisma) {
    try {
      const { PrismaClient } = require("@prisma/client");
      _prisma = new PrismaClient({
        log: ["error"],
      });
    } catch {
      // Return a mock that returns empty results
      _prisma = createMockPrisma();
    }
  }
  return _prisma;
}

function createMockPrisma(): any {
  const handler: ProxyHandler<any> = {
    get(_target, prop) {
      if (prop === "$connect" || prop === "$disconnect") return async () => {};
      // Return a model proxy
      return new Proxy(
        {},
        {
          get(_, method) {
            // All query methods return empty results
            return async (..._args: any[]) => {
              if (method === "findMany" || method === "groupBy") return [];
              if (method === "findUnique" || method === "findFirst") return null;
              if (method === "create" || method === "update") return { id: "mock" };
              if (method === "delete") return { id: "mock" };
              if (method === "count") return 0;
              return null;
            };
          },
        }
      );
    },
  };
  return new Proxy({}, handler);
}

export const prisma = new Proxy({} as any, {
  get(_target, prop) {
    const client = getPrisma();
    const val = client[prop];
    return typeof val === "function" ? val.bind(client) : val;
  },
});
