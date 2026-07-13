# ✧ Atlas of Knowledge

An interactive **dependency graph of human knowledge**. Each node is a *course*
(a subject you can learn); edges are prerequisites. Nodes are arranged into
horizontal levels by **topological depth** (how deep in the prerequisite chain a
subject sits), colored by your **completion** status, and expand on click to show
a description, requirements, free & paid resources, and a list of the
topics covered.

https://ethanvieira.github.io/atlas-of-knowledge/

## Contributing

The atlas is meant to be **crowd-sourced** — every course and resource lives in a
plain data file under [`js/data/`](js/data/), one file per field, so anyone can
add to a discipline they know. See **[CONTRIBUTING.md](CONTRIBUTING.md)** for the
schema and workflow. Before opening a PR, run the validator:

```bash
node scripts/validate.js
```

It checks the whole catalog for duplicate ids, dangling prerequisites,
dependency cycles and malformed entries — and the same check runs in CI on every
pull request.

## License

- **Code** (the site's HTML/CSS/JS and tooling) — [MIT](LICENSE).
- **Course data** (everything under [`js/data/`](js/data/): courses,
  descriptions, topics, prerequisites and resource lists) —
  [CC BY-SA 4.0](LICENSE-DATA.md).