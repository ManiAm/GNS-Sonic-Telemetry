
import grpc
import gnmi_pb2
import gnmi_pb2_grpc

# SONiC gNMI endpoint
TARGET = "10.10.10.100:8080"

# Authentication
USERNAME = "admin"
PASSWORD = "YourPassword"

# 1. Create gRPC channel
channel = grpc.insecure_channel(TARGET)

# 2. Create gNMI client stub
stub = gnmi_pb2_grpc.gNMIStub(channel)

# 3. Build OpenConfig path
path = gnmi_pb2.Path(
    origin="openconfig-interfaces",
    elem=[
        gnmi_pb2.PathElem(name="interfaces"),
        gnmi_pb2.PathElem(name="interface", key={"name": "Ethernet0"}),
        gnmi_pb2.PathElem(name="state"),
        gnmi_pb2.PathElem(name="counters"),
    ]
)

# 4. Build GetRequest
request = gnmi_pb2.GetRequest(
    path=[path],
    encoding=gnmi_pb2.Encoding.JSON_IETF
)

# 5. Send metadata (authentication)
metadata = [
    ("username", USERNAME),
    ("password", PASSWORD),
]

# 6. Execute RPC
response = stub.Get(request, metadata=metadata)

print(response)
