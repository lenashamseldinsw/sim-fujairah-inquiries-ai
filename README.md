# نبض الفجيرة - Fujairah Pulse AI Platform

## 📖 Overview

**نبض الفجيرة** (Fujairah Pulse) is an AI-powered platform for analyzing customer inquiries and complaints. The project uses a **dual-implementation strategy**:

- **`demo/`**: Stable, production-ready demo version with simulated outputs (main branch)
- **`real/`**: Full agentic AI implementation with real analysis pipelines (real branch)

**See [CLAUDE.md](CLAUDE.md) for full development guide.**

---

## 🚀 Quick Start

### Demo Version (Stable, Pre-built Reports)
```bash
make demo
# Or: cd demo && streamlit run app.py
```
Opens at `http://localhost:8501` with automatic report extraction and caching.

### Real Version (AI-Powered Analysis)
```bash
cd real && streamlit run app_inq_comp.py
```
Unified app supporting both inquiries and complaints flows with 6-stage AI pipelines.

---

## 📁 Project Structure

```
sim-fujairah-inquiries-ai/
├── CLAUDE.md                  # Development guide (READ THIS FIRST)
├── README.md                  # This file (project overview)
├── demo/                      # Stable demo version
│   ├── README.md             # Demo-specific setup & features
│   ├── app.py                # Streamlit UI
│   └── analysis/             # Demo analyzer with extraction
├── real/                      # AI-powered real version
│   ├── README.md             # Real-specific setup & features
│   ├── app_inq_comp.py       # Unified dual-flow UI
│   ├── inquiries-flow/       # Inquiries pipeline
│   └── complaints-flow/      # Complaints pipeline
├── sword_word_builder/       # Shared Word generation utilities
├── Makefile                  # Convenience commands
└── requirements.txt          # Python dependencies
```

---

## 🎯 Which Version Should I Use?

| Need | Version | Command |
|------|---------|---------|
| **See pre-built sample reports** | demo | `make demo` |
| **Run AI analysis on real data** | real | `cd real && streamlit run app_inq_comp.py` |
| **Develop demo features** | demo | Edit `demo/` folder |
| **Develop AI pipelines** | real | Edit `real/` folder |

---

## 📚 Documentation

- **[CLAUDE.md](CLAUDE.md)**: Full development guide, architecture, and workflows
- **[demo/README.md](demo/README.md)**: Demo version setup and features
- **[real/README.md](real/README.md)**: Real version setup and features
- **Memory**: See `.claude/projects/.../memory/MEMORY.md` for implementation notes

---

## 🔧 Development

### Making Changes

**To demo version** (UI, extraction, caching):
```bash
cd demo && streamlit run app.py
```

**To real version** (AI pipelines, analysis logic):
```bash
cd real && streamlit run app_inq_comp.py
```

Both versions are independent. Changes to demo don't affect real and vice versa.

### Running Tests

```bash
# Demo extraction tests
cd demo && python test_adaptive_system.py

# Real pipeline tests (if available)
cd real && python test_pipeline.py
```

---

## 🌍 Deployment

### Streamlit Cloud

Push the repo to GitHub and deploy from https://streamlit.io/cloud:
- For demo: Select `demo/app.py`
- For real: Select `real/app_inq_comp.py`

### Docker

See individual README files in `demo/` and `real/` for Docker setup.

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Port 8501 in use | `streamlit run app.py --server.port 8502` |
| ModuleNotFoundError | Make sure you're in `demo/` or `real/` folder |
| Reports not displaying | Check `demo/inquiries-output/` or `demo/complaints-output/` folders exist |
| Cache not working | Delete `*/cache/` folders and re-run |

---

## 📝 Key Files

- **[CLAUDE.md](CLAUDE.md)**: Complete development instructions (must read)
- **[Makefile](Makefile)**: Quick start commands
- **[demo/README.md](demo/README.md)**: Demo version details
- **[real/README.md](real/README.md)**: Real version details

---

**Developed for**: حكومة الفجيرة | Fujairah Government  
**Last Updated**: June 2026
