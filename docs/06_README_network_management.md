
# Network Management Protocols

Network management protocols define how external systems such as monitoring platforms, controllers, and automation frameworks communicate with network devices. These protocols allow management systems to retrieve operational data, configure device parameters, and monitor the health and performance of network infrastructure in a structured and programmatic way.

## SNMP (Simple Network Management Protocol)

SNMP is one of the earliest standardized management protocols and is still widely used for monitoring. It operates using a polling model, where a management system repeatedly queries devices to retrieve metrics such as CPU utilization, interface counters, and memory usage. SNMP organizes this information using Management Information Bases (MIBs), which define the structure of the data that can be retrieved from a device.

In small environments this polling approach works well, but in very large networks constant polling can create significant overhead. When thousands of devices are polled simultaneously, it can produce the so-called **thundering herd** problem, where both network bandwidth and device CPU resources become overloaded. Additionally, SNMP was not designed for complex configuration management. Its data models were relatively rigid and not well suited for representing hierarchical configuration data.

Although SNMP technically supports configuration changes, it has historically been used mainly for monitoring. As networks became larger and automation became more important, engineers increasingly relied on device Command Line Interfaces (CLI) for configuration. However, automating CLI interactions required parsing text output, a fragile technique commonly referred to as **screen scraping**. Even small formatting changes in CLI output could break automation scripts, making large-scale automation difficult to maintain.


## The Move to Model-Driven Management

To address the limitations of SNMP and CLI-based approaches, the networking industry moved toward model-driven network management. This approach separates the data model from the transport protocol, allowing devices and management systems to exchange structured data defined by a common schema. As part of this effort, the IETF standardized [YANG](./05_README_yang.md), a data modeling language designed specifically for network configuration and operational data.

A common misconception is that YANG is a network protocol. In reality, YANG only defines the structure of configuration and operational data. It does not define how that data is transmitted. Instead, several protocols use YANG-defined models to exchange data between systems:

- YANG defines the schema (the data model).
- NETCONF, RESTCONF, and gNMI transport the data between systems.

```text
CLI / Screen Scraping
        ↓
SNMP + MIB
        ↓
YANG Data Models
        ↓
NETCONF / RESTCONF / gNMI
```

<img src="../pics/yang_usage.png" alt="segment" width="500">

| Feature       | NETCONF                         | RESTCONF                    | gNMI                                  |
| ------------- | ------------------------------- | --------------------------- | ------------------------------------- |
| Transport     | SSH                             | HTTP/HTTPS                  | HTTP/2 (gRPC)                         |
| Data Encoding | XML                             | XML or JSON                 | JSON or Protobuf                      |
| Typical Use   | Device configuration management | REST-based automation tools | Streaming telemetry and configuration |


### NETCONF (Network Configuration Protocol)

NETCONF was the first protocol designed to work closely with YANG. It was standardized by the IETF to replace older management approaches that relied on CLI or SNMP-based configuration. NETCONF introduced a structured, programmatic interface that allows configuration changes to be performed in a reliable and standardized way.

NETCONF operates over a persistent SSH connection between the client (such as a network automation tool) and the network device. Communication occurs using XML-encoded Remote Procedure Calls (RPCs). The structure of configuration and operational data is defined using YANG data models, which specify the schema and validation rules for the data exchanged between the client and the device. In this model-driven architecture, YANG defines the structure of the data, while NETCONF provides the protocol used to transport and manipulate that data.

<img src="../pics/netconf.png" alt="segment" width="600">

One of the strongest capabilities of NETCONF is its support for **transactional** configuration management. Devices maintain configuration datastores such as running, candidate, and startup. Administrators can lock a configuration datastore to prevent concurrent modifications, apply configuration changes to the candidate datastore, validate those changes against the YANG model, and then commit them atomically. If a configuration fails validation or produces unexpected results, the changes can be rolled back. These features make NETCONF particularly well suited for large enterprise networks where configuration consistency and safety are critical.

The main limitation of NETCONF is its reliance on XML encoding, which tends to be verbose and computationally expensive to parse. Processing large XML payloads can place additional overhead on both the client and the network device, especially in environments with large configuration datasets or high-frequency management operations.


### RESTCONF

RESTCONF was introduced to make YANG-based network management easier to integrate with modern web technologies. It uses the same YANG data models as NETCONF but exposes them through standard HTTP-based interfaces.

In RESTCONF, the hierarchical structure defined in a YANG model is mapped directly to HTTP Uniform Resource Identifiers (URIs). Clients interact with network devices using standard HTTP methods such as `GET` to retrieve data, `POST` to create resources, `PUT` or `PATCH` to modify existing data, and `DELETE` to remove configuration elements. RESTCONF supports both XML and JSON encodings, with JSON being commonly used because it integrates well with modern programming languages and web frameworks.

The primary advantage of RESTCONF is its ease of integration. Because it relies on widely used web protocols and data formats, developers can interact with network devices using common tools such as HTTP libraries, REST clients, or web frameworks. This makes RESTCONF especially useful for integrating network management functions into web applications, dashboards, or lightweight automation scripts.

However, RESTCONF operates using stateless HTTP connections, which means each request is handled independently. Unlike NETCONF, it does not provide the same robust transactional mechanisms, such as datastore locking and coordinated configuration commits. Additionally, repeated HTTP requests may introduce overhead compared to protocols that maintain long-lived connections.


### gNMI

Refer to [gNMI guide](./08_README_gnmi.md) for more details.
