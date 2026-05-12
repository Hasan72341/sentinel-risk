import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ToastProvider } from '../renderer/components/Toast';
import Layout from '../renderer/components/Layout';
import Dashboard from '../renderer/pages/Dashboard';
import Analysis from '../renderer/pages/Analysis';
import Reports from '../renderer/pages/Reports';
import History from '../renderer/pages/History';
import Settings from '../renderer/pages/Settings';
import AICopilot from '../renderer/pages/AICopilot';
import Prediction from '../renderer/pages/Prediction';
import DocumentIntelligence from '../renderer/pages/DocumentIntelligence';
import Benchmarking from '../renderer/pages/Benchmarking';
import Compliance from '../renderer/pages/Compliance';
import Consolidation from '../renderer/pages/Consolidation';
import TimeSeries from '../renderer/pages/TimeSeries';
import FinancialEngineering from '../renderer/pages/FinancialEngineering';
import Backtest from '../renderer/pages/Backtest';
import FuzzyMCDM from '../renderer/pages/FuzzyMCDM';
import FactorAnalysis from '../renderer/pages/FactorAnalysis';
import BlackLitterman from '../renderer/pages/BlackLitterman';
import Sentiment from '../renderer/pages/Sentiment';
import StochasticCalculus from '../renderer/pages/StochasticCalculus';
import NetworkAnalysis from '../renderer/pages/NetworkAnalysis';
import CausalInference from '../renderer/pages/CausalInference';
import ReinforcementLearning from '../renderer/pages/ReinforcementLearning';
import FuzzyNeural from '../renderer/pages/FuzzyNeural';
import AdvancedOptimization from '../renderer/pages/AdvancedOptimization';
import CreditExposure from '../renderer/pages/CreditExposure';
import CreditRating from '../renderer/pages/CreditRating';
import CounterpartyMonitor from '../renderer/pages/CounterpartyMonitor';
import VarBacktesting from '../renderer/pages/VarBacktesting';
import StressTesting from '../renderer/pages/StressTesting';
import ModelMonitoring from '../renderer/pages/ModelMonitoring';
import PotentialExposure from '../renderer/pages/PotentialExposure';
import InitialMargin from '../renderer/pages/InitialMargin';
import AsiaMarkets from '../renderer/pages/AsiaMarkets';
import PublicFilings from '../renderer/pages/PublicFilings';

export default function App() {
  return (
    <HashRouter>
      <ToastProvider>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/analysis" element={<Analysis />} />
            <Route path="/public-filings" element={<PublicFilings />} />
            <Route path="/analysis/:id" element={<Analysis />} />
            <Route path="/ai-copilot" element={<AICopilot />} />
            <Route path="/prediction" element={<Prediction />} />
            <Route path="/document-intelligence" element={<DocumentIntelligence />} />
            <Route path="/benchmarking" element={<Benchmarking />} />
            <Route path="/compliance" element={<Compliance />} />
            <Route path="/consolidation" element={<Consolidation />} />
            <Route path="/credit-rating" element={<CreditRating />} />
            <Route path="/counterparty-monitor" element={<CounterpartyMonitor />} />
            <Route path="/var-backtesting" element={<VarBacktesting />} />
            <Route path="/stress-testing" element={<StressTesting />} />
            <Route path="/model-monitoring" element={<ModelMonitoring />} />
            <Route path="/potential-exposure" element={<PotentialExposure />} />
            <Route path="/initial-margin" element={<InitialMargin />} />
            <Route path="/asia-markets" element={<AsiaMarkets />} />
            <Route path="/time-series" element={<TimeSeries />} />
            <Route path="/financial-engineering" element={<FinancialEngineering />} />
            <Route path="/credit-exposure" element={<CreditExposure />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/fuzzy-mcdm" element={<FuzzyMCDM />} />
            <Route path="/factor-analysis" element={<FactorAnalysis />} />
            <Route path="/black-litterman" element={<BlackLitterman />} />
            <Route path="/sentiment" element={<Sentiment />} />
            <Route path="/stochastic-calculus" element={<StochasticCalculus />} />
            <Route path="/network-analysis" element={<NetworkAnalysis />} />
            <Route path="/causal-inference" element={<CausalInference />} />
            <Route path="/reinforcement-learning" element={<ReinforcementLearning />} />
            <Route path="/fuzzy-neural" element={<FuzzyNeural />} />
            <Route path="/advanced-optimization" element={<AdvancedOptimization />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/history" element={<History />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Layout>
      </ToastProvider>
    </HashRouter>
  );
}
