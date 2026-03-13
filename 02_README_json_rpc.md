
# JSON-RPC Example

Before exploring more advanced RPC frameworks such as gRPC, it is useful to examine a simpler RPC protocol to understand the core concepts of remote procedure calls. JSON-RPC is a lightweight RPC protocol that uses JSON as the message format and typically relies on HTTP as the transport mechanism. Because of its simplicity and minimal overhead, JSON-RPC demonstrates how a client can invoke functions on a remote server and receive results as if they were local function calls.

In the following example, a Python server exposes a simple function `add(x, y)` using the [jsonrpclib-pelix](https://github.com/tcalmant/jsonrpclib/) library. The server listens on localhost:4000 and registers the `add` function as a remotely callable method. Once the server is running, it waits for incoming RPC requests. When a request arrives, the JSON-RPC framework automatically handles the networking layer, parses the incoming JSON message, invokes the appropriate function, and sends the result back to the client.

On the client side, the Server object acts as a proxy (stub) for the remote service. The client code calls `proxy.add(5, 6)` exactly as it would call a normal local function. However, the proxy intercepts the call, serializes the method name and parameters into a JSON-RPC request, and sends it to the server over HTTP. The server executes the `add` function and returns the result in a JSON response. The client library then deserializes the response and returns the value to the calling program, making the remote execution appear identical to a local function call.

Here is the server code:

```python
# server.py

from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCServer


def add(x, y):
    """A simple function that adds two numbers."""
    print(f"Received: x={x} ({type(x)}), y={y} ({type(y)})")
    return x + y


def main():

    server = SimpleJSONRPCServer(('localhost', 4000))
    server.register_function(add, 'add')

    print("Starting server on localhost:4000")
    server.serve_forever()


if __name__ == '__main__':

    main()
```

Here is the client code:

```python
# client.py

from jsonrpclib import Server


def main():

    proxy = Server("http://localhost:4000")

    result = proxy.add(5, 6)
    print(f"Result: {result}")


if __name__ == '__main__':

    main()
```

Install the json-rpc package:

    pip install jsonrpclib-pelix

Invoke the server script in a terminal:

    python3 server.py

You will see the following output:

    Starting server on localhost:4000

In a new terminal, invoke the client script:

    python3 client.py

You should get an output like:

    Result: 11

You can also try calling an unsupported method in client:

```python
result = proxy.subtract(6, 5)
print(f"Result: {result}")
```

This example also illustrates an important characteristic of JSON-RPC: it is weakly typed. Unlike strongly typed RPC frameworks, JSON-RPC does not enforce parameter types before sending a request. The client can send values of any type, and the server must validate and handle them appropriately. For example, if the client calls `proxy.add("10", 20)`, the request is still transmitted to the server because the protocol itself does not enforce type constraints.

```json
{
    "jsonrpc": "2.0",
    "id": "07171586-f9b0-4976-99f7-0da63f1bc098",
    "method": "add",
    "params": [
        "10",
        20
    ]
}
```

The server then receives the request, attempts to execute the `add` function with the provided parameters, and returns an error.

Examining this workflow provides a clear understanding of the fundamental RPC mechanics: method invocation, parameter serialization, network transmission, remote execution, and response handling. Once these core ideas are understood through JSON-RPC, it becomes easier to appreciate how more advanced frameworks such as gRPC build on the same RPC principles while adding stronger typing, better performance, and support for advanced communication patterns such as streaming.
