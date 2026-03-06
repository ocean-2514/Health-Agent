# Extracted from transformerAgent/backend/tools/physics_tool.py
import datetime
import math
import numpy as np

class TransformerRULCalculator:
    def __init__(self):
        self.DP_START = 1200.0
        self.DP_END = 200.0
        self.Ea = 111000.0
        self.R_GAS = 8.314
        self.A0_REF = 6.0e7
        self.k_hist_std = 2.5e-9
        self.k_min_base = 1.0e-8

        self.WEIGHTS_OIL_PARAMS = {'bdv': 3, 'water': 4, 'acid': 1, 'ift': 2}
        self.WEIGHTS_DGA_PARAMS = {'H2': 2, 'CH4': 3, 'CO': 1, 'CO2': 1, 'C2H4': 3, 'C2H6': 3, 'C2H2': 5}

    def _map_raw_score_to_hif(self, raw_score, max_raw_score):
        if max_raw_score <= 1: return 4.0
        normalized = (raw_score - 1) / (max_raw_score - 1)
        return max(0.0, min(4.0, 4.0 * (1.0 - normalized)))

    def calculate_health_index(self, oil_data, dga_data, furan_data):
        oil_sum = sum(oil_data.get(k, 1) * w for k, w in self.WEIGHTS_OIL_PARAMS.items())
        oil_w_sum = sum(self.WEIGHTS_OIL_PARAMS.values())
        hif_oil = self._map_raw_score_to_hif(oil_sum / oil_w_sum, 3)

        dga_sum = sum(dga_data.get(k, 1) * w for k, w in self.WEIGHTS_DGA_PARAMS.items())
        dga_w_sum = sum(self.WEIGHTS_DGA_PARAMS.values())
        hif_dga = self._map_raw_score_to_hif(dga_sum / dga_w_sum, 6)

        furan_map = {'A': 4, 'B': 3, 'C': 2, 'D': 1, 'E': 0}
        hif_furan = furan_map.get(furan_data.get('level', 'A'), 4)

        num = (8 * hif_oil + 10 * hif_dga + 5 * hif_furan)
        den = 4 * (8 + 10 + 5)
        return round((num / den) * 100.0, 2)

    def calculate_apparent_age(self, hi_score):
        if hi_score >= 99.0: return 0.1
        if hi_score <= 10.0: return 50.0
        hi_norm = hi_score / 100.0
        try:
            return max(0.1, 10.0 * (math.log(1.0 / hi_norm - 1.0) + 5.3))
        except ValueError:
            return 40.0

    def calculate_current_dp(self, t_now):
        t_hours = t_now * 8760.0
        denom = (1.0 / self.DP_START) + (self.k_hist_std * t_hours)
        return int(1.0 / denom)

    def calculate_hotspot_temp(self, Ta, K):
        term1 = 55.0 * (((1 + 5.0 * (K ** 2)) / 6.0) ** 0.8)
        term2 = 29.9 * (K ** 1.6)
        return Ta + term1 + term2

    def calculate_future_aging_rate(self, Ths, moisture_content):
        Tk = Ths + 273.15
        A = self.A0_REF * moisture_content
        k_thermal = A * math.exp(-self.Ea / (self.R_GAS * Tk))
        return k_thermal + self.k_min_base

    def predict_rul_raw(self, dp_now, k_future):
        if dp_now <= self.DP_END: return 0.0
        loss_term = (1.0 / self.DP_END) - (1.0 / dp_now)
        return (loss_term / k_future) / 8760.0

    def predict_rul(self, dp_now, k_future, penalty_factor=1.0):
        rul_years = self.predict_rul_raw(dp_now, k_future) * penalty_factor
        if dp_now < 800 and rul_years > 30.0: return 30.0
        if rul_years > 40.0: return 40.0
        return round(rul_years, 2)

    def run_monte_carlo_simulation(self, input_data, n_iterations=1000):
        rul_results = []
        base_load = float(input_data.get('future_load', 0.8))
        base_temp = float(input_data.get('ambient_temp', 20.0))
        base_moisture = float(input_data.get('moisture', 1.5))
        base_penalty = float(input_data.get('penalty_factor', 1.0))

        hi = self.calculate_health_index(
            input_data.get('oil', {}), input_data.get('dga', {}), input_data.get('furan', {})
        )
        age = self.calculate_apparent_age(hi)
        dp_base = self.calculate_current_dp(age)

        for _ in range(n_iterations):
            sim_load = max(0.1, np.random.normal(base_load, max(0.01, abs(base_load) * 0.15)))
            sim_temp = np.random.normal(base_temp, 2.0)
            sim_moisture = max(0.5, np.random.normal(base_moisture, 0.1))
            sim_dp = dp_base + np.random.normal(0, 10)

            ths = self.calculate_hotspot_temp(sim_temp, sim_load)
            k_fut = self.calculate_future_aging_rate(ths, sim_moisture)

            rul = self.predict_rul_raw(sim_dp, k_fut) * base_penalty
            model_noise = np.random.normal(0, 1.5)
            final_rul = max(0.1, rul + model_noise)

            if final_rul < 40.0:
                rul_results.append(final_rul)

        if not rul_results:
            rul_results = [10.0]

        p10 = np.percentile(rul_results, 10)
        p50 = np.percentile(rul_results, 50)
        p90 = np.percentile(rul_results, 90)
        std_dev = np.std(rul_results)
        confidence = max(0, min(100, 100 - std_dev * 5))

        mu = np.mean(rul_results)
        sigma = np.std(rul_results)
        if sigma < 0.5: sigma = 0.5

        x_start = max(0, mu - 4 * sigma)
        x_end = min(45, mu + 4 * sigma)

        x_points = np.linspace(x_start, x_end, 18)

        y_points = (1 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_points - mu) / sigma) ** 2)

        dist_data = {
            "x": [round(float(x), 2) for x in x_points],
            "y": [round(float(y), 4) for y in y_points]
        }

        return {
            "p10_conservative": round(p10, 2),
            "p50_median": round(p50, 2),
            "p90_optimistic": round(p90, 2),
            "confidence_score": int(confidence),
            "distribution_coord": dist_data
        }

    def get_life_deduction_data(self, hi_start, penalty=1.0, years=25, start_year=2026):
        base_decay_rate = 0.03
        decay_k = base_decay_rate * penalty
        
        x_years = list(range(0, years + 1))
        real_years = [start_year + y for y in x_years]
        y_hi = [round(hi_start * math.exp(-decay_k * t), 1) for t in x_years]
        y_hi = [max(0.0, hi) for hi in y_hi]
        return {"x": real_years, "y": y_hi}

    def run_full_analysis(self, input_data):
        hi = self.calculate_health_index(
            input_data.get('oil', {}), input_data.get('dga', {}), input_data.get('furan', {})
        )
        age = self.calculate_apparent_age(hi)
        dp = self.calculate_current_dp(age)
        K = input_data.get('future_load', 0.8)
        Ta = input_data.get('ambient_temp', 20.0)
        M = input_data.get('moisture', 1.5)
        P_factor = input_data.get('penalty_factor', 1.0)

        ths = self.calculate_hotspot_temp(Ta, K)
        k_fut = self.calculate_future_aging_rate(ths, M)
        rul = self.predict_rul(dp, k_fut, penalty_factor=P_factor)

        # Forced overrides from external defect detection
        forced_rul = input_data.get('forced_rul')
        if forced_rul is not None:
            rul = float(forced_rul)
        
        forced_hi = input_data.get('forced_hi')
        if forced_hi is not None:
            hi = float(forced_hi)

        mc_result = self.run_monte_carlo_simulation(input_data)
        
        now_year = datetime.datetime.now().year
        deduction_curve = self.get_life_deduction_data(hi, penalty=P_factor, years=25, start_year=now_year)

        return {
            "health_index": hi,
            "predicted_rul_years": rul,
            "uncertainty_analysis": mc_result,
            "health_deduction_curve": deduction_curve,
            "ai_penalty_factor_applied": P_factor
        }
