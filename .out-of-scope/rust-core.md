# Rust core

Date: 2026-10-14
Decision: no Rust or compiled core.
Reason: a toolchain or signed binaries would reintroduce a dependency; contracts stay language-neutral so a hot-path binary stays possible later.
