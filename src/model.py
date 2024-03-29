"""
Functions to build predictive model of admissions.

TODO:
- Fix estimation of uncertainty (95% CI is too narrow!)
- Show how to build hierarchy (need to load data for different locations)
"""

from typing import Optional

import jax.numpy as jnp
import numpyro
import numpyro.distributions as dist
import plotly.express as px
import plotly.graph_objects as go
from jax import Array, random
from numpyro.diagnostics import hpdi
from numpyro.infer import MCMC, NUTS

from .download_data import get_admissions_data

PROP_TRAIN = 0.75


def admissions_model(timestamp: Array, admissions: Optional[Array] = None) -> None:
    """Builds admissions model using numpyro api

    Args:
        timestamp (Array): Timestamp data (must be numeric type)
        admissions (Optional[Array], optional): Observed admissions data. Defaults to None.
    """
    # Hyper-parameters
    intercept_loc = 1e5
    intercept_scale = 1e4
    gradient_loc = 1e3
    gradient_scale = 1e2
    noise_rate = 10.0

    # Priors
    intercept = numpyro.sample("intercept", dist.Normal(intercept_loc, intercept_scale))
    gradient = numpyro.sample("gradient", dist.Normal(gradient_loc, gradient_scale))
    admissions_loc = intercept + gradient * timestamp
    admissions_scale = numpyro.sample("noise", dist.Exponential(noise_rate))
    numpyro.sample(
        "admissions", dist.Normal(admissions_loc, admissions_scale), obs=admissions
    )


def plot_model_results(
    x: Array, y_observed: Array, y_predicted: Array, y_hpdi: Array
) -> None:
    fig = px.line(x=x, y=y_predicted)
    extra_traces = [
        go.Scatter(
            x=x,
            y=y_hpdi[0],
            fill=None,
            mode="lines",
            line_color="lightblue",
            name="Lower CI",
        ),
        go.Scatter(
            x=x,
            y=y_hpdi[1],
            fill="tonexty",
            mode="lines",
            line_color="lightblue",
            name="Upper CI",
        ),
        list(px.scatter(x=x, y=y_observed).select_traces()),
    ]

    for traces in extra_traces:
        fig.add_traces(traces)

    y_offset = 0.1  # 10% above/below
    y_min = min(y_observed) - y_offset * abs(max(y_observed))
    y_max = (1 + y_offset) * max(y_observed)
    fig.update_yaxes(range=[y_min, y_max])

    fig.show()


if __name__ == "__main__":
    df_admissions = get_admissions_data()

    timestamps = jnp.arange(len(df_admissions.index))
    admissions = jnp.array(df_admissions["Total Emergency Admissions"].values)

    # Train/test split
    n_train = int(PROP_TRAIN * timestamps.size)
    timestamps_train = timestamps[:n_train]
    timestamps_test = timestamps[n_train:]
    admissions_train = admissions[:n_train]
    admissions_test = admissions[n_train:]

    # Fit the model
    nuts_kernel = NUTS(admissions_model)
    mcmc = MCMC(nuts_kernel, num_warmup=500, num_samples=1000)
    rng_key = random.PRNGKey(0)
    mcmc.run(rng_key, timestamps_train, admissions=admissions_train, extra_fields=())
    mcmc.print_summary()

    # Compute empirical posterior distribution over mu
    samples_1 = mcmc.get_samples()
    posterior_mu = jnp.expand_dims(
        samples_1["gradient"], -1
    ) * timestamps_test + jnp.expand_dims(samples_1["intercept"], -1)
    admissions_pred = jnp.mean(posterior_mu, axis=0)
    admissions_hpdi = hpdi(posterior_mu, 0.95)

    plot_model_results(
        x=timestamps_test,
        y_observed=admissions_test,
        y_predicted=admissions_pred,
        y_hpdi=admissions_hpdi,
    )
