import math
from ortools.sat.python import cp_model

def allocate(streams, throughput, reserved=0, harm_floor=0.8,
           realism_bound=0.30, unc_cap=0.15) -> dict:
    avail = throughput - reserved
    if avail < 0:
        avail = 0
        
    total_n = sum(s['n'] for s in streams)
    
    # Calculate derived values safely
    for s in streams:
        n_s = s['n']
        s['b_s'] = (avail * n_s / total_n) if total_n > 0 else 0
        s['h_s'] = s.get('historical_share', 0.0) * avail
        
        p_s = s.get('p', 0.0)
        if math.isnan(p_s): 
            p_s = 0.0
        s['p_s'] = p_s

    # Generate relaxation sequence
    # 1. harm_floor relaxes 0.8 -> 0.75 -> ... -> 0.0
    # 2. realism_bound relaxes 0.30 -> 0.35 -> ... -> 1.0
    
    harm_steps = [max(0.0, harm_floor - 0.05 * i) for i in range(math.ceil(harm_floor / 0.05) + 1)]
    realism_steps = [min(1.0, realism_bound + 0.05 * i) for i in range(math.ceil((1.0 - realism_bound) / 0.05) + 1)]
    
    sequences = []
    for hf in harm_steps:
        sequences.append((hf, realism_bound))
    for rb in realism_steps[1:]:
        sequences.append((0.0, rb))
        
    for current_hf, current_rb in sequences:
        model = cp_model.CpModel()
        variables = {}
        
        lo_hi_valid = True
        
        for s in streams:
            sid = s['id']
            n_s = s['n']
            b_s = s['b_s']
            h_s = s['h_s']
            low_conf = s.get('low_confidence', False)
            
            # C2 fairness floor
            c2_floor = math.floor(current_hf * b_s)
            
            # C3 realism bound
            c3_lo = h_s * (1.0 - current_rb)
            c3_hi = h_s * (1.0 + current_rb)
            
            # C4 unc_cap for low_confidence
            c4_lo = 0.0
            c4_hi = float(n_s)
            if low_conf:
                c4_lo = b_s * (1.0 - unc_cap)
                c4_hi = b_s * (1.0 + unc_cap)
            
            # Combine all bounds
            lo_bound = max(0, c2_floor, math.ceil(c3_lo), math.ceil(c4_lo))
            hi_bound = min(n_s, math.floor(c3_hi), math.floor(c4_hi))
            
            # Clamp to [0, n_s]
            lo_bound = int(max(0, min(n_s, lo_bound)))
            hi_bound = int(max(0, min(n_s, hi_bound)))
            
            if lo_bound > hi_bound:
                lo_hi_valid = False
                break
                
            variables[sid] = model.NewIntVar(lo_bound, hi_bound, f"x_{sid}")
            
        if not lo_hi_valid:
            continue
            
        # C1
        if variables:
            model.Add(sum(variables.values()) <= avail)
            
        # Objective: minimise sum( round(1000 * p_s) * (n_s - x_s) )
        obj_expr = []
        for s in streams:
            sid = s['id']
            p_s = s['p_s']
            n_s = s['n']
            cost = round(1000 * p_s)
            obj_expr.append(cost * (n_s - variables[sid]))
            
        if obj_expr:
            model.Minimize(sum(obj_expr))
            
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5.0
        status = solver.Solve(model)
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            allocation = {}
            for sid, var in variables.items():
                allocation[sid] = solver.Value(var)
                
            relaxations = []
            if abs(current_hf - harm_floor) > 1e-5:
                relaxations.append(f"fairness floor relaxed {harm_floor:.2f} -> {current_hf:.2f}")
            if abs(current_rb - realism_bound) > 1e-5:
                relaxations.append(f"realism bound relaxed {realism_bound:.2f} -> {current_rb:.2f}")
                
            before_crossings = sum(s['p_s'] * (s['n'] - s['b_s']) for s in streams)
            after_crossings = sum(s['p_s'] * (s['n'] - allocation[s['id']]) for s in streams)
            
            return {
                "feasible": True,
                "allocation": allocation,
                "before": {"crossings": before_crossings},
                "after": {"crossings": after_crossings},
                "relaxed_constraints": relaxations,
                "baseline": {s['id']: s['b_s'] for s in streams}
            }
            
    # Infeasible after full relaxation, fallback to greedy fill
    # as per STOP CONDITION
    for s in streams:
        c2_floor = math.floor(harm_floor * s['b_s'])
        c3_hi = math.floor(s['h_s'] * (1.0 + realism_bound))
        c3_lo = math.ceil(s['h_s'] * (1.0 - realism_bound))
        s['x_s'] = min(s['n'], max(c2_floor, c3_lo))
        if s['x_s'] > c3_hi:
            s['x_s'] = c3_hi

    allocated = sum(s['x_s'] for s in streams)
    remainder = avail - allocated
    
    sorted_streams = sorted(streams, key=lambda s: s['p_s'], reverse=True)
    for s in sorted_streams:
        if remainder <= 0: break
        c3_hi = math.floor(s['h_s'] * (1.0 + realism_bound))
        cap = min(s['n'], c3_hi)
        can_add = cap - s['x_s']
        if can_add > 0:
            add = min(remainder, can_add)
            s['x_s'] += add
            remainder -= add
            
    allocation = {s['id']: s['x_s'] for s in streams}
    
    return {
        "feasible": True,
        "allocation": allocation,
        "before": {"crossings": sum(s['p_s'] * (s['n'] - s['b_s']) for s in streams)},
        "after": {"crossings": sum(s['p_s'] * (s['n'] - s['x_s']) for s in streams)},
        "relaxed_constraints": ["Problem remains infeasible after full relaxation, used greedy fallback"],
        "baseline": {s['id']: s['b_s'] for s in streams}
    }
