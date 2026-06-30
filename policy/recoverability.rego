package telco.recoverability

# Deterministic recoverability floor for the Track 1 stand-in lab (HANDOVER §5,
# Phase 1). This is the PDP that sits at the NETCONF transaction boundary: given
# a model-aware delta (candidate vs running) it returns permit/deny so the
# mediator can commit-and-permit or deny-and-discard.
#
# It encodes ONLY the illustrative rails enumerated in the handover:
#   - restart one instance        -> permit (recoverable)
#   - turn a hardening setting off -> permit (recoverable)
#   - delete-everything class      -> deny   (unrecoverable)
#   - power-off-all class          -> deny   (unrecoverable)
#
# THIS IS NOT a production recoverability policy. The catastrophic classes
# below are generic, illustrative heuristics for the development floor.
#
# `deny` is a set of {rule, reason} objects. Empty set => permit. The floor is
# deny-on-match / default-permit: anything not matched by a catastrophic rule
# lands in the "recoverable zone" where (in Stage two) only the agent's
# judgment operates.

# --- deny rule 1: delete-everything (whole /hardening subtree removed) ---
deny contains v if {
	input.hardening_deleted == true
	v := {
		"rule": "delete-everything:hardening",
		"reason": "transaction removes the entire /hardening configuration subtree (unrecoverable)",
	}
}

# --- deny rule 2: delete-everything (all managed-function instances removed) ---
deny contains v if {
	input.managed_function.total_before > 0
	input.managed_function.deleted_count == input.managed_function.total_before
	v := {
		"rule": "delete-everything:managed-function",
		"reason": "transaction deletes ALL managed-function instances (unrecoverable)",
	}
}

# --- deny rule 3: power-off-all (every managed-function locked in one txn) ---
deny contains v if {
	input.managed_function.total_after > 0
	input.managed_function.locked_after_total == input.managed_function.total_after
	input.managed_function.newly_locked_count > 0
	v := {
		"rule": "power-off-all:managed-function",
		"reason": "transaction locks ALL managed-function instances at once (total service outage, no in-service element left to recover from)",
	}
}

permit := count(deny) == 0

decision := {
	"permit": permit,
	"denies": deny,
}
