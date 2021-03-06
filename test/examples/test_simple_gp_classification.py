import os
import math
import torch
import unittest
import gpytorch
from torch import nn, optim
from torch.autograd import Variable
from gpytorch.kernels import RBFKernel
from gpytorch.means import ConstantMean
from gpytorch.likelihoods import BernoulliLikelihood
from gpytorch.random_variables import GaussianRandomVariable


def train_data(cuda=False):
    train_x = Variable(torch.linspace(0, 1, 10))
    train_y = Variable(torch.sign(torch.cos(train_x.data * (4 * math.pi))))
    if cuda:
        return train_x.cuda(), train_y.cuda()
    else:
        return train_x, train_y


class GPClassificationModel(gpytorch.models.VariationalGP):
    def __init__(self, train_x):
        super(GPClassificationModel, self).__init__(train_x)
        self.mean_module = ConstantMean(constant_bounds=[-1e-5, 1e-5])
        self.covar_module = RBFKernel(log_lengthscale_bounds=(-5, 6))
        self.register_parameter(
            'log_outputscale',
            nn.Parameter(torch.Tensor([0])),
            bounds=(-5, 6),
        )

    def forward(self, x):
        mean_x = self.mean_module(x)
        covar_x = self.covar_module(x)
        covar_x = covar_x.mul(self.log_outputscale.exp().expand_as(covar_x))
        latent_pred = GaussianRandomVariable(mean_x, covar_x)
        return latent_pred


class TestSimpleGPClassification(unittest.TestCase):
    def setUp(self):
        if os.getenv('UNLOCK_SEED') is None or os.getenv('UNLOCK_SEED').lower() == 'false':
            self.rng_state = torch.get_rng_state()
            torch.manual_seed(0)

    def tearDown(self):
        if hasattr(self, 'rng_state'):
            torch.set_rng_state(self.rng_state)

    def test_classification_error(self):
        train_x, train_y = train_data()
        likelihood = BernoulliLikelihood()
        model = GPClassificationModel(train_x.data)
        mll = gpytorch.mlls.VariationalMarginalLogLikelihood(
            likelihood,
            model,
            n_data=len(train_y),
        )

        # Find optimal model hyperparameters
        model.train()
        likelihood.train()
        optimizer = optim.Adam(model.parameters(), lr=0.1)
        optimizer.n_iter = 0
        for _ in range(50):
            optimizer.zero_grad()
            output = model(train_x)
            loss = -mll(output, train_y)
            loss.backward()
            optimizer.n_iter += 1
            optimizer.step()

        # Set back to eval mode
        model.eval()
        likelihood.eval()
        test_preds = (
            likelihood(model(train_x)).mean().ge(0.5).float().
            mul(2).sub(1).squeeze()
        )
        mean_abs_error = torch.mean(torch.abs(train_y - test_preds) / 2)
        assert(mean_abs_error.data.squeeze()[0] < 1e-5)

    def test_classification_fast_pred_var(self):
        with gpytorch.fast_pred_var():
            train_x, train_y = train_data()
            likelihood = BernoulliLikelihood()
            model = GPClassificationModel(train_x.data)
            mll = gpytorch.mlls.VariationalMarginalLogLikelihood(
                likelihood,
                model,
                n_data=len(train_y),
            )

            # Find optimal model hyperparameters
            model.train()
            likelihood.train()
            optimizer = optim.Adam(model.parameters(), lr=0.1)
            optimizer.n_iter = 0
            for _ in range(50):
                optimizer.zero_grad()
                output = model(train_x)
                loss = -mll(output, train_y)
                loss.backward()
                optimizer.n_iter += 1
                optimizer.step()

            # Set back to eval mode
            model.eval()
            likelihood.eval()
            test_preds = (
                likelihood(model(train_x)).mean().ge(0.5).float().
                mul(2).sub(1).squeeze()
            )

            mean_abs_error = torch.mean(torch.abs(train_y - test_preds) / 2)
            self.assertLess(mean_abs_error.data.squeeze()[0], 1e-5)

    def test_classification_error_cuda(self):
        if torch.cuda.is_available():
            train_x, train_y = train_data(cuda=True)
            likelihood = BernoulliLikelihood().cuda()
            model = GPClassificationModel(train_x.data).cuda()
            mll = gpytorch.mlls.VariationalMarginalLogLikelihood(
                likelihood,
                model,
                n_data=len(train_y),
            )

            # Find optimal model hyperparameters
            model.train()
            optimizer = optim.Adam(model.parameters(), lr=0.1)
            optimizer.n_iter = 0
            for _ in range(50):
                optimizer.zero_grad()
                output = model(train_x)
                loss = -mll(output, train_y)
                loss.backward()
                optimizer.n_iter += 1
                optimizer.step()

            # Set back to eval mode
            model.eval()
            test_preds = (
                likelihood(model(train_x)).mean().ge(0.5).float().
                mul(2).sub(1).squeeze()
            )
            mean_abs_error = torch.mean(torch.abs(train_y - test_preds) / 2)
            self.assertLess(mean_abs_error.data.squeeze()[0], 1e-5)


if __name__ == '__main__':
    unittest.main()
