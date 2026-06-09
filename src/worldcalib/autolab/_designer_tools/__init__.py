"""In-sandbox client scripts for AutoLab designer mode.

These modules are not imported in-process; they are copied into a designer
workspace and run by the proposer agent inside its sandbox (which has no
harbor). They talk to the host-side ``EvalBridge`` purely through files. The
package exists so setuptools ships the scripts and the optimizer can locate
them via ``importlib.resources`` / ``__file__``.
"""
