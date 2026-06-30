package telco.recoverability_test

import data.telco.recoverability as rec

# Unit tests for the recoverability floor. Run with:
#   docker run --rm -v ./policy:/policies openpolicyagent/opa:1.9.0-static test /policies -v

base_mf := {
	"total_before": 3,
	"total_after": 3,
	"deleted_count": 0,
	"locked_after_total": 0,
	"newly_locked_count": 0,
}

# --- recoverable -> permit ---

test_permit_restart_one_instance if {
	rec.permit with input as {
		"hardening_deleted": false,
		"management_interface_deleted": false,
		"managed_function": {
			"total_before": 3, "total_after": 3, "deleted_count": 0,
			"locked_after_total": 1, "newly_locked_count": 1,
		},
	}
}

test_permit_turn_audit_log_off if {
	rec.permit with input as {"hardening_deleted": false, "managed_function": base_mf}
}

test_permit_lock_two_of_three if {
	rec.permit with input as {
		"hardening_deleted": false,
		"managed_function": {
			"total_before": 3, "total_after": 3, "deleted_count": 0,
			"locked_after_total": 2, "newly_locked_count": 2,
		},
	}
}

# --- catastrophic -> deny ---

test_deny_delete_entire_hardening if {
	not rec.permit with input as {"hardening_deleted": true, "managed_function": base_mf}
}

test_deny_delete_all_managed_functions if {
	not rec.permit with input as {
		"hardening_deleted": false,
		"managed_function": {
			"total_before": 3, "total_after": 0, "deleted_count": 3,
			"locked_after_total": 0, "newly_locked_count": 0,
		},
	}
}

test_deny_power_off_all if {
	not rec.permit with input as {
		"hardening_deleted": false,
		"managed_function": {
			"total_before": 3, "total_after": 3, "deleted_count": 0,
			"locked_after_total": 3, "newly_locked_count": 3,
		},
	}
}

# partial delete (2 of 3) is still recoverable -> permit
test_permit_delete_two_of_three if {
	rec.permit with input as {
		"hardening_deleted": false,
		"managed_function": {
			"total_before": 3, "total_after": 1, "deleted_count": 2,
			"locked_after_total": 0, "newly_locked_count": 0,
		},
	}
}
