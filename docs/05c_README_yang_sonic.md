# YANG Models in SONiC

This document catalogs the YANG models shipped with SONiC and explains the SONiC-specific conventions — annotations, extensions, and Jinja2 templates — that adapt standard YANG to the SONiC Redis-centric architecture.

> For general YANG language concepts, see [YANG Introduction](05_README_yang.md), [YANG Syntax Reference](05a_README_yang_syntax.md), and [YANG Validation](05b_README_yang_validation.md). For how these models are used at runtime by the gNMI and RESTCONF pipelines, see [gNMI in SONiC](09_README_gnmi_sonic.md).

## Two Sets of YANG Models — and Why

SONiC uses two distinct sets of YANG models within the [sonic-buildimage](https://github.com/sonic-net/sonic-buildimage) repository. They are not independent systems — they serve different stages of the same configuration pipeline.

```text
                  ┌──────────────────────┐
  gNMI / RESTCONF │   Translib           │  Uses OpenConfig models + annotations
  client request  │   (translation layer)│  to parse paths and map to Redis
                  └──────────┬───────────┘
                             │
                  ┌──────────▼───────────┐
  Config CLI ───► │   CVL                │  Uses native sonic-*.yang models
  (also writes    │   (validation)       │  to validate CONFIG_DB writes
   to CONFIG_DB)  └──────────┬───────────┘
                             │
                  ┌──────────▼───────────┐
                  │   CONFIG_DB (Redis)  │
                  └──────────────────────┘
```

**Native `sonic-*.yang` models** define the CONFIG_DB schema — the structure and constraints of what is actually stored in Redis. The Config Validation Library (CVL) uses these models to validate every CONFIG_DB write, regardless of which interface initiated it: gNMI, RESTCONF, CLI, or `config reload`. These models are always in the path.

**Management framework models** (OpenConfig, gNSI, annotations) define the northbound API — the YANG paths that external gNMI and RESTCONF clients see. Translib uses these models to translate between OpenConfig paths and Redis table operations. After translation, Translib calls CVL, which validates the resulting data against the native models before writing to CONFIG_DB.

| Scenario                    | OpenConfig models (Translib) | Native `sonic-*.yang` (CVL) |
| --------------------------- | :--------------------------: | :-------------------------: |
| Config CLI → CONFIG_DB      | —                            | ✓                           |
| gNMI / RESTCONF → CONFIG_DB | ✓                            | ✓                          |

### Source Locations

The two model sets live in separate directories within the sonic-buildimage repository.

**Management framework models** — [sonic-mgmt-common](https://github.com/sonic-net/sonic-mgmt-common) submodule:

```text
src/sonic-mgmt-common/models/yang/
├── *.yang           → 17 top-level models (OpenConfig, gNSI, IETF)
├── annotations/     → 8 transformer annotations (*-annot.yang)
├── common/          → 52 shared dependencies (IETF types, OpenConfig submodules)
├── extensions/      → 2 deviations + 1 OpenConfig YANG extension
├── sonic/           → 4 SONiC-specific models (mgmt framework)
│   └── common/      → 2 shared definitions (sonic-extension, sonic-common)
└── version.xml      → Bundle version definition
```

**Native YANG models** — directly in [sonic-buildimage](https://github.com/sonic-net/sonic-buildimage/tree/master/src/sonic-yang-models) (not a submodule):

```text
src/sonic-yang-models/
├── yang-models/      → 145 static .yang files
├── yang-templates/   → 4 Jinja2 templates (.yang.j2)
├── tests/            → YANG model test configurations
└── doc/              → CONFIG_DB schema documentation
```

## Standard OpenConfig and gNSI Models

SONiC supports OpenConfig YANG models, which are vendor-neutral schemas used widely across the networking industry. These models define standardized paths and data structures that gNMI clients use when interacting with devices. SONiC also ships gNSI (gRPC Network Security Infrastructure) models for certificate, credential, authorization, and path-level access control. Together, these form the northbound management API surface.

| Model | Area |
| ----- | ---- |
| `openconfig-interfaces` | Interface configuration and state |
| `openconfig-if-ethernet` | Ethernet-specific interface parameters |
| `openconfig-if-ip` | IPv4 / IPv6 interface addressing |
| `openconfig-acl` | Access control lists and rules |
| `openconfig-lacp` | Link Aggregation Control Protocol |
| `openconfig-lldp` | Link Layer Discovery Protocol |
| `openconfig-p4rt` | P4Runtime programmable forwarding pipeline |
| `openconfig-platform` | Hardware platform and component inventory |
| `openconfig-platform-boot-loader` | Boot loader version and management |
| `openconfig-platform-transceiver` | Optical transceiver monitoring |
| `openconfig-sampling-sflow` | sFlow sampling configuration |
| `openconfig-system` | Hostname, NTP, AAA, DNS, logging, CPU/memory |
| `ietf-yang-library` | YANG module set capability reporting (RFC 7895) |
| `gnsi-authz` | gRPC-level authorization policies |
| `gnsi-certz` | Certificate management |
| `gnsi-credentialz` | Credential rotation and management |
| `gnsi-pathz` | Path-level access control |

These top-level models import 52 shared dependency modules from the `common/` directory (IETF base types, OpenConfig submodules for platform components, type libraries, and so on). An additional 8 **annotation files** and 3 **platform customization files** (deviations and extensions) adapt the OpenConfig models for the SONiC platform.

## SONiC Native YANG Models

For SONiC-specific functionality not covered by OpenConfig, the system defines **149 native YANG modules** across two source locations:

- `src/sonic-yang-models/yang-models/` — 145 static `.yang` files used by CVL for CONFIG_DB validation.

- `src/sonic-yang-models/yang-templates/` — 4 Jinja2 templates (`sonic-acl`, `sonic-policer`, `sonic-extension`, `sonic-types`) that generate build-variant-specific `.yang` files (e.g., CVL vs. management framework variants).

The table below groups every native model by functional area.

| Category | Models | Key Files |
| -------- | :----: | --------- |
| **Interfaces & L2** | 22 | `sonic-port`, `sonic-portchannel`, `sonic-interface`, `sonic-loopback-interface`, `sonic-vlan`, `sonic-vlan-sub-interface`, `sonic-mgmt_interface`, `sonic-mgmt_port`, `sonic-breakout_cfg`, `sonic-lldp`, `sonic-spanning-tree`, `sonic-storm-control`, `sonic-macsec`, `sonic-mac-move-guard`, `sonic-fabric-port`, `sonic-fabric-monitor`, `sonic-fast-linkup`, `sonic-voq-inband-interface`, `sonic-system-port`, `sonic-cable-length`, `sonic-fdb-sync`, `sonic-neigh` |
| **BGP & Routing** | 19 | `sonic-bgp-global`, `sonic-bgp-neighbor`, `sonic-bgp-peergroup`, `sonic-bgp-peerrange`, `sonic-bgp-prefix-list`, `sonic-bgp-monitor`, `sonic-bgp-common`, `sonic-bgp-aggregate-address`, `sonic-bgp-allowed-prefix`, `sonic-bgp-bbr`, `sonic-bgp-device-global`, `sonic-bgp-internal-neighbor`, `sonic-bgp-sentinel`, `sonic-bgp-voq-chassis-neighbor`, `sonic-bmp`, `sonic-route-common`, `sonic-route-map`, `sonic-routing-policy-sets`, `sonic-static-route` |
| **Overlay & Tunnels** | 11 | `sonic-vxlan`, `sonic-vnet`, `sonic-nvgre-tunnel`, `sonic-tunnel`, `sonic-subnet-decap`, `sonic-evpn`, `sonic-srv6`, `sonic-mclag`, `sonic-mux-cable`, `sonic-mux-linkmgr`, `sonic-peer-switch` |
| **QoS & Buffering** | 24 | `sonic-buffer-pg`, `sonic-buffer-pool`, `sonic-buffer-profile`, `sonic-buffer-queue`, `sonic-buffer-port-egress-profile-list`, `sonic-buffer-port-ingress-profile-list`, `sonic-queue`, `sonic-scheduler`, `sonic-wred-profile`, `sonic-pfcwd`, `sonic-port-qos-map`, `sonic-dot1p-tc-map`, `sonic-dscp-tc-map`, `sonic-dscp-fc-map`, `sonic-tc-queue-map`, `sonic-tc-dscp-map`, `sonic-tc-priority-group-map`, `sonic-pfc-priority-queue-map`, `sonic-pfc-priority-priority-group-map`, `sonic-mpls-tc-map`, `sonic-exp-fc-map`, `sonic-lossless-traffic-pattern`, `sonic-default-lossless-buffer-parameter`, `sonic-trimming` |
| **ACL & Security** | 9 | `sonic-acl`\*, `sonic-policer`\*, `sonic-nat`, `sonic-copp`, `sonic-pbh`, `sonic-hash`, `sonic-fips`, `sonic-passwh`, `sonic-ssh-server` |
| **Network Services** | 10 | `sonic-dhcp-server`, `sonic-dhcp-server-ipv4`, `sonic-dhcpv4-relay`, `sonic-dhcpv6-relay`, `sonic-dns`, `sonic-ntp`, `sonic-sflow`, `sonic-snmp`, `sonic-mirror-session`, `sonic-static-anycast-gateway` |
| **System & Device** | 26 | `sonic-device_metadata`, `sonic-device_neighbor`, `sonic-device_neighbor_metadata`, `sonic-system-aaa`, `sonic-system-tacacs`, `sonic-system-radius`, `sonic-system-ldap`, `sonic-system-defaults`, `sonic-feature`, `sonic-warm-restart`, `sonic-syslog`, `sonic-logger`, `sonic-console`, `sonic-serial-console`, `sonic-banner`, `sonic-crm`, `sonic-flex_counter`, `sonic-versions`, `sonic-chassis-module`, `sonic-smart-switch`, `sonic-kubernetes_master`, `sonic-ztp`, `sonic-kdump`, `sonic-memory-statistics`, `sonic-platform-node`, `sonic-sai-profile` |
| **Telemetry & Monitoring** | 14 | `sonic-telemetry`, `sonic-telemetry_client`, `sonic-high-frequency-telemetry`, `sonic-gnmi`, `sonic-grpcclient`, `sonic-restapi`, `sonic-alarm`, `sonic-asic-sensors`, `sonic-heartbeat`, `sonic-stormond-config`, `sonic-xcvrd-log`, `sonic-auto_techsupport`, `sonic-suppress-asic-sdk-health-event`, `sonic-leak-control` |
| **Events** | 7 | `sonic-event`, `sonic-events-bgp`, `sonic-events-common`, `sonic-events-dhcp-relay`, `sonic-events-host`, `sonic-events-swss`, `sonic-events-syncd` |
| **DASH** | 1 | `sonic-dash` |
| **Other** | 4 | `sonic-debug-counter`, `sonic-fine-grained-ecmp`, `sonic-vrf`, `sonic-mgmt_vrf` |
| **Shared / Support** | 2 | `sonic-types`\*, `sonic-extension`\* |

\* Generated from Jinja2 templates at build time.

## Annotation Files

Because SONiC stores configuration and state in Redis rather than directly in YANG structures, it uses annotation files (typically ending in `-annot.yang`) to provide declarative mappings between YANG elements and Redis tables, keys, and fields. For straightforward one-to-one mappings, these annotations are sufficient on their own. For complex translations that require programmatic logic, Translib delegates the work to custom transformer code (see [Request Processing in gNMI](09_README_gnmi_sonic.md#request-processing-and-data-flow)).

```text
openconfig-acl-annot.yang
openconfig-interfaces-annot.yang
openconfig-mclag-annot.yang
openconfig-platform-annot.yang
openconfig-sampling-sflow-annot.yang
openconfig-system-annot.yang
sonic-extensions.yang              ← extension definitions (not an annotation itself)
sonic-showtech-annot.yang
```

The six `*-annot.yang` files contain the actual YANG-to-Redis mappings. `sonic-extensions.yang` lives in the same directory but serves a different role: it defines the extension keywords (`sonic-ext:db-name`, `sonic-ext:key-delim`, etc.) that the annotation files and native models reference.

## SONiC Extension Definitions

The [`sonic-extension`](https://github.com/sonic-net/sonic-buildimage/blob/master/src/sonic-mgmt-common/models/yang/sonic/common/sonic-extension.yang) module declares custom YANG extensions specific to the SONiC platform. These extensions bridge the gap between standard YANG modeling constructs and SONiC's Redis-centric architecture. For background on how YANG extensions work in general, see the [YANG Language Reference — Extension in YANG](05a_README_yang_syntax.md#extension-in-yang).

| Extension | Purpose | Example Usage |
| --------- | ------- | ------------- |
| `sonic-ext:db-name` | Specifies which Redis database a container maps to | `sonic-ext:db-name "APPL_DB"` |
| `sonic-ext:key-delim` | Overrides the default `\|` key delimiter | `sonic-ext:key-delim ":"` |
| `sonic-ext:map-list` | Marks a list as a mapping table | `sonic-ext:map-list "true"` |
| `sonic-ext:custom-validation` | Registers a platform-specific validation callback | `sonic-ext:custom-validation ValidateStpFeatureEnabled` |
| `sonic-ext:dependent-on` | Declares table-level ordering dependencies | `sonic-ext:dependent-on "STP_LIST"` |

Below is a condensed excerpt from the upstream [`sonic-spanning-tree.yang`](https://github.com/sonic-net/sonic-buildimage/blob/master/src/sonic-mgmt-common/cvl/testdata/schema/sonic-spanning-tree.yang) that shows `custom-validation` and `dependent-on` in action:

```yang
import sonic-extension {
    prefix sonic-ext;
}

container STP {
    list STP_LIST {
        sonic-ext:custom-validation ValidateStpFeatureEnabled;
        key "keyleaf";
        // ...
    }
}

container STP_VLAN {
    list STP_VLAN_LIST {
        key "name";
        sonic-ext:dependent-on "STP_LIST";
        // ...
    }
}
```

The `custom-validation` extension registers a named callback (`ValidateStpFeatureEnabled`) that CVL invokes when the `STP_LIST` is created or modified. This allows SONiC to enforce platform-specific rules that cannot be expressed with standard YANG constraints. The `dependent-on` extension tells the system that `STP_VLAN_LIST` depends on `STP_LIST`, so during creation the parent is written first, and during deletion the dependent is removed first.

The following excerpt from the upstream [`sonic-vxlan.yang`](https://github.com/sonic-net/sonic-buildimage/blob/master/src/sonic-mgmt-common/cvl/testdata/schema/sonic-vxlan.yang) shows `db-name` and `key-delim` mapping state data to a non-default Redis database:

```yang
container VXLAN_TUNNEL_TABLE {
    sonic-ext:db-name "STATE_DB";
    sonic-ext:key-delim ":";
    config false;
    description "State DB VXLAN tunnel table";
    // ...
}
```

By default, SONiC YANG models map to CONFIG_DB with `|` as the key delimiter. The `db-name` extension overrides the target database (here `STATE_DB`), and `key-delim` overrides the delimiter (here `:`). These extensions allow a single YANG model to span multiple Redis databases, which is essential because SONiC distributes data across CONFIG_DB, STATE_DB, APPL_DB, and COUNTERS_DB.
