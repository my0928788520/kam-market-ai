# Replay Version Compatibility Matrix

All frozen Sprint 4 public contracts currently use version `1.0`: Input, Timeline, Serialization, Fixture, Runner, Frame, Frame Serialization, Evaluator Adapter, Evaluation Contract/Serialization, Decision Adapter, Dashboard Read Model/Comparison/Serialization/Fixture, Presenter/Serialization/Fixture, WSGI Adapter, and UI. Each typed adapter accepts its declared supported `1.0` source version and rejects incompatible sources fail-closed.
