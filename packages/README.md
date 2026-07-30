# Core Modules

`packages/` contains independently testable, product-neutral Core Modules.

The M1 module graph is:

```text
foundation
  <- authoring-domain
  <- project-io
  <- project-cooker
  <- audio-runtime
  <- provider-sdk
  <- application-facade
```

Every Module owns a `module.json`, SemVer, CMake target, public include
boundary, and direct tests. Dependencies use exact Module versions.

Product Assembly, UI, cloud deployment, and product-specific Provider choices
do not belong here.
