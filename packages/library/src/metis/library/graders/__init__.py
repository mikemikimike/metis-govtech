"""metis.library.graders: the grader catalogue for the METIS evaluation suite.

Canonical import path: ``from metis.library.graders import XGrader``, which is also the FQN a
criterion names in specification.yaml (``metis.library.graders.XGrader``).

Every class exported here is a concrete ``metis.library.grader.Grader``. The contract itself
lives outside this package so that the wizard's catalogue, which lists every class this
package exports, only ever offers real graders. One file per grader is a layout choice with no
semantic weight.

It exports no graders yet. The example graders are in ``metis.library.graders.demo``, which is
deliberately not re-exported here, so the wizard has nothing to offer until real graders land
(#470).
"""
